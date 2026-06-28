from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from src.agents.tool_runtime.jobs.models import ToolJob, ToolJobStatus
from src.agents.tool_runtime.jobs.repository import ToolJobRepository
from src.skills.registry import SkillRegistry, get_skill_registry
from src.skills.repository import AgentSkillRepository, get_agent_skill_repository

log = logging.getLogger(__name__)

TOOL_JOB_STALE_AFTER_SECONDS = 10 * 60


class ToolJobService:
    def __init__(
        self,
        *,
        repository: ToolJobRepository | None = None,
        skill_repository: AgentSkillRepository | None = None,
        skill_registry: SkillRegistry | None = None,
    ):
        self.repository = repository or ToolJobRepository()
        self.skill_repository = skill_repository or get_agent_skill_repository()
        self.skill_registry = skill_registry or get_skill_registry()

    def create_skill_action_job(
        self,
        *,
        owner_email: str,
        actor_email: str,
        actor_id: str,
        agent_id: str,
        conversation_id: str,
        user_message_id: str | None,
        skill_id: str,
        installed_skill_id: str,
        action: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> ToolJob:
        return self.repository.create(
            ToolJob(
                owner_email=owner_email,
                actor_email=actor_email,
                actor_id=actor_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                tool_name="execute_skill_action",
                skill_id=skill_id,
                installed_skill_id=installed_skill_id,
                action=action,
                arguments=arguments,
                context=context,
            )
        )

    def start_skill_action_job(self, job: ToolJob) -> None:
        asyncio.create_task(self.execute_skill_action_job(job.job_id))

    async def execute_skill_action_job(self, job_id: str) -> None:
        job = self.repository.find_by_id(job_id)
        if not job:
            log.error("Async tool job disappeared before execution: %s", job_id)
            return

        self.repository.mark_running(job_id, f"Running {job.action or job.tool_name}...")
        try:
            if not job.agent_id or not job.installed_skill_id or not job.skill_id or not job.action:
                raise ValueError("Tool job is missing skill execution metadata")

            installed = self.skill_repository.find_by_id(job.agent_id, job.installed_skill_id)
            if not installed or not installed.enabled:
                raise ValueError("Skill is no longer installed or enabled for this agent")

            config = self.skill_repository.get_runtime_config(installed)
            result = await self.skill_registry.execute_action(
                skill_id=job.skill_id,
                action_name=job.action,
                arguments=job.arguments,
                config=config,
                context=job.context,
            )
            self.repository.mark_succeeded(job_id, result)
        except Exception as exc:
            log.error("Async tool job failed: %s", job_id, exc_info=True)
            self.repository.mark_failed(job_id, str(exc))

    def check_job_for_agent(
        self,
        *,
        job_id: str,
        owner_email: str,
        actor_email: str,
        agent_id: str,
        conversation_id: str,
    ) -> dict[str, Any]:
        job = self.repository.find_by_id(job_id)
        if not job:
            raise ValueError("Tool job not found")
        if job.owner_email != owner_email:
            raise ValueError("Tool job not found")
        if job.agent_id and job.agent_id != agent_id:
            raise ValueError("Tool job not found")
        if job.conversation_id and job.conversation_id != conversation_id:
            raise ValueError("Tool job not found")
        if actor_email != owner_email and job.actor_email != actor_email:
            raise ValueError("Tool job not found")
        job = self._fail_stale_job(job)
        return job.to_status_payload()

    def _fail_stale_job(self, job: ToolJob) -> ToolJob:
        if job.status not in {ToolJobStatus.QUEUED, ToolJobStatus.RUNNING}:
            return job

        reference_time = job.started_at or job.created_at
        elapsed_seconds = (datetime.now(timezone.utc) - _as_aware_utc(reference_time)).total_seconds()
        if elapsed_seconds <= TOOL_JOB_STALE_AFTER_SECONDS:
            return job

        return self.repository.mark_failed(
            job.job_id,
            "Async tool job became stale before completion. The background execution may have been interrupted; please retry the action.",
        )


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
