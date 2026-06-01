"""Scheduler dispatch orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.scheduler.models import (
    Schedule,
    ScheduleRun,
    ScheduleRunStatus,
    ScheduleStatus,
    ScheduleTargetType,
)
from src.scheduler.repository import ScheduleRunAlreadyExists, SchedulerRepository
from src.scheduler.service import SchedulerService
from src.scheduler.executors import (
    AgentScheduledMessageExecutor,
    AutomationScheduledRunExecutor,
    ScheduleTargetExecutor,
)


class SchedulerDispatcher:
    """Loads schedules, enforces idempotency, and records dispatch results."""

    def __init__(
        self,
        repository: SchedulerRepository | None = None,
        service: SchedulerService | None = None,
        executors: dict[ScheduleTargetType, ScheduleTargetExecutor] | None = None,
    ):
        self.repository = repository or SchedulerRepository()
        self.service = service or SchedulerService(repository=self.repository)
        self.executors = executors or {
            ScheduleTargetType.AGENT_MESSAGE: AgentScheduledMessageExecutor(),
            ScheduleTargetType.AUTOMATION_RUN: AutomationScheduledRunExecutor(),
        }

    async def dispatch(
        self,
        *,
        schedule_id: str,
        owner_email: str,
        scheduled_for: datetime,
    ) -> ScheduleRun:
        schedule = self.service.get_schedule(schedule_id, owner_email)
        run = ScheduleRun(
            run_id=ScheduleRun.deterministic_run_id(schedule_id, scheduled_for),
            schedule_id=schedule_id,
            owner_email=owner_email,
            scheduled_for=scheduled_for,
            status=ScheduleRunStatus.RUNNING,
            target_type=schedule.target_type,
            target_ref=self._target_ref(schedule),
            started_at=datetime.now(timezone.utc),
        )
        try:
            self.repository.save_run_once(run)
        except ScheduleRunAlreadyExists:
            run.status = ScheduleRunStatus.SKIPPED
            run.output = {"reason": "duplicate_dispatch"}
            run.completed_at = datetime.now(timezone.utc)
            return run

        if schedule.status != ScheduleStatus.ACTIVE:
            run.status = ScheduleRunStatus.SKIPPED
            run.output = {"reason": f"schedule_{schedule.status.value}"}
            run.completed_at = datetime.now(timezone.utc)
            self.repository.save_run(run)
            return run

        try:
            executor = self.executors[schedule.target_type]
            run.output = await executor.execute(schedule, scheduled_for)
            run.status = ScheduleRunStatus.SUCCEEDED
            self.service.mark_dispatched(schedule, scheduled_for)
        except Exception as exc:
            run.status = ScheduleRunStatus.FAILED
            run.error = str(exc)
        finally:
            run.completed_at = datetime.now(timezone.utc)
            self.repository.save_run(run)
        return run

    def _target_ref(self, schedule: Schedule) -> dict[str, Any]:
        if schedule.target_type == ScheduleTargetType.AGENT_MESSAGE:
            return {
                "agent_id": schedule.target.get("agent_id"),
                "conversation_id": schedule.target.get("conversation_id"),
            }
        if schedule.target_type == ScheduleTargetType.AUTOMATION_RUN:
            return {
                "automation_id": schedule.target.get("automation_id"),
                "trigger_id": schedule.target.get("trigger_id"),
            }
        return {}
