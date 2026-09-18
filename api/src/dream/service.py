"""Orchestrates resumable, session-atomic Dream passes."""

from __future__ import annotations

from asyncio import CancelledError
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from src.agents.repository import AgentRepository
from src.config import settings as app_settings
from src.conversations.repository import ConversationRepository
from src.dream.actions import DreamActionContext, DreamActionExecutor
from src.dream.models import (
    DreamActionLog,
    DreamActionOutcome,
    DreamCursor,
    DreamRun,
    DreamRunStatus,
    DreamSettings,
)
from src.dream.planner import DreamPlanner
from src.dream.redaction import redact
from src.dream.repository import DreamRepository
from src.dream.sessions import SessionChunker
from src.dream.window import DreamWindowBuilder
from src.llm.credentials import load_provider_credentials
from src.llm.providers import get_llm_provider
from src.memory.repository import MemoryRepository
from src.messages.repositories import MessageRepository, get_message_repository
from src.scheduler.models import CreateScheduleRequest, ScheduleTargetType, UpdateScheduleRequest
from src.scheduler.service import SchedulerService, SchedulerValidationError
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository
from src.token_usage.service import TokenUsageService


class DreamNotConfiguredError(ValueError):
    pass


class DreamService:
    def __init__(
        self,
        *,
        dream_repository: DreamRepository | None = None,
        memory_repository: MemoryRepository | None = None,
        conversation_repository: ConversationRepository | None = None,
        message_repository: MessageRepository | None = None,
        agent_repository: AgentRepository | None = None,
        provider_settings_repository: ProviderSettingsRepository | None = None,
        planner: DreamPlanner | None = None,
        token_usage_service: TokenUsageService | None = None,
        scheduler_service: SchedulerService | None = None,
    ) -> None:
        self.dream_repository = dream_repository or DreamRepository()
        self.memory_repository = memory_repository or MemoryRepository()
        self.conversation_repository = conversation_repository or ConversationRepository()
        self.message_repository = message_repository or get_message_repository()
        self.agent_repository = agent_repository or AgentRepository()
        self.provider_settings_repository = provider_settings_repository or get_provider_settings_repository()
        self.planner = planner or DreamPlanner()
        self.token_usage_service = token_usage_service or TokenUsageService()
        self.scheduler_service = scheduler_service or SchedulerService()

    @staticmethod
    def schedule_id_for(agent_id: str, user_id: str) -> str:
        return f"dream:{agent_id}:{user_id}"

    def ensure_schedule(self, agent_id: str, user_id: str, owner_email: str, dream_settings: DreamSettings) -> None:
        schedule_id = self.schedule_id_for(agent_id, user_id)
        enabled = dream_settings.enabled and app_settings.dream_enabled
        request = CreateScheduleRequest(
            schedule_id=schedule_id,
            name="Nightly memory dream",
            cron_expression=dream_settings.cron_expression,
            timezone=dream_settings.timezone,
            target_type=ScheduleTargetType.DREAM_RUN,
            target={"agent_id": agent_id, "user_id": user_id},
            source_type="dream",
            source_ref={"agent_id": agent_id, "user_id": user_id},
            enabled=enabled,
        )
        try:
            self.scheduler_service.get_schedule(schedule_id, owner_email)
        except SchedulerValidationError:
            self.scheduler_service.create_schedule(request, owner_email, owner_email)
            return
        self.scheduler_service.update_schedule(
            schedule_id,
            UpdateScheduleRequest(
                name=request.name,
                cron_expression=request.cron_expression,
                timezone=request.timezone,
                target=request.target,
                source_ref=request.source_ref,
                enabled=enabled,
            ),
            owner_email,
        )

    def delete_schedule(self, agent_id: str, user_id: str, owner_email: str) -> None:
        try:
            self.scheduler_service.delete_schedule(self.schedule_id_for(agent_id, user_id), owner_email)
        except SchedulerValidationError:
            pass

    async def dream(
        self,
        *,
        agent_id: str,
        user_id: str,
        owner_email: str,
        mode: Literal["backfill", "daily", "manual"] = "daily",
    ) -> DreamRun:
        run = DreamRun(run_id=str(uuid4()), agent_id=agent_id, user_id=user_id, owner_email=owner_email, mode=mode)
        self.dream_repository.save_run(run)
        if not self.dream_repository.try_acquire_run_lease(
            agent_id, user_id, run.run_id, app_settings.dream_run_lease_seconds
        ):
            return self._finish(run, DreamRunStatus.SKIPPED, "another dream run is already active")
        try:
            dream_settings = self.dream_repository.find_settings(owner_email)
            if not app_settings.dream_enabled or not dream_settings or (not dream_settings.enabled and mode != "manual"):
                return self._finish(run, DreamRunStatus.SKIPPED, "dreaming is disabled")
            if not dream_settings.provider_name or not dream_settings.model_name:
                return self._finish(run, DreamRunStatus.SKIPPED, "dream model is not configured")
            agent = self.agent_repository.find_agent_by_id(agent_id, owner_email)
            if not agent or agent.agent_architecture != "krishna-memgpt":
                return self._finish(run, DreamRunStatus.SKIPPED, "agent does not support core memory")

            self.memory_repository.initialize_default_blocks(agent_id, user_id)
            cursor = self.dream_repository.find_cursor(agent_id, user_id)
            window = DreamWindowBuilder(
                conversation_repository=self.conversation_repository,
                message_repository=self.message_repository,
                page_size=app_settings.dream_message_page_size,
            ).build(
                agent_id=agent_id, owner_email=owner_email,
                session_timeout_minutes=agent.session_timeout_minutes,
                settings=dream_settings, cursor=cursor, requested_mode=mode,
            )
            run.mode, run.window_start, run.window_end = window.mode, window.start, window.end
            run.sessions_considered = len(window.sessions)
            if not window.sessions:
                return self._finish(run, DreamRunStatus.SKIPPED, "no_new_sessions")

            provider_settings = self.provider_settings_repository.find_by_provider(owner_email, dream_settings.provider_name)
            if not provider_settings:
                return self._finish(run, DreamRunStatus.FAILED, f"provider '{dream_settings.provider_name}' is not configured")
            credentials = await load_provider_credentials(
                provider_name=dream_settings.provider_name,
                provider_settings=provider_settings,
                provider_settings_repo=self.provider_settings_repository,
            )
            provider = get_llm_provider(dream_settings.provider_name)
            cursor = cursor or DreamCursor(agent_id=agent_id, user_id=user_id)
            action_index = 0
            for session_index, session in enumerate(window.sessions):
                if self._at_budget(run, dream_settings):
                    run.sessions_remaining = len(window.sessions) - session_index
                    break
                chunks = SessionChunker().chunk(session, app_settings.dream_chunk_max_words, app_settings.dream_window_overlap_words)
                prior_summary = ""

                for chunk in chunks:
                    if not self.dream_repository.renew_run_lease(
                        agent_id, user_id, run.run_id, app_settings.dream_run_lease_seconds
                    ):
                        raise RuntimeError("lost Dream run lease")
                    if not any(message.role == "user" for message in chunk.messages):
                        run.chunks_skipped_empty += 1
                        continue
                    redacted_messages = [message.model_copy(update={"content": redact(message.content)[0]}) for message in chunk.messages]
                    planning_chunk = chunk.__class__(
                        session=chunk.session, index=chunk.index, total=chunk.total, messages=redacted_messages,
                        granularity=chunk.granularity, window_of_message_id=chunk.window_of_message_id,
                        window_index=chunk.window_index, window_total=chunk.window_total,
                    )
                    planning = await self.planner.plan(
                        provider=provider, credentials=credentials, model_name=dream_settings.model_name,
                        chunk=planning_chunk,
                        block_definitions=self.memory_repository.get_block_definitions(agent_id, user_id),
                        core_memories=self.memory_repository.get_all_core_memories(agent_id, user_id),
                        prior_summary=prior_summary,
                        stall_timeout_seconds=app_settings.dream_planner_timeout_seconds,
                    )
                    prior_summary = planning.plan.session_summary
                    run.chunks_planned += 1
                    run.prompt_tokens += planning.prompt_tokens
                    run.completion_tokens += planning.completion_tokens
                    self._record_usage(
                        owner_email, agent_id, dream_settings.model_name,
                        planning.prompt_tokens, planning.completion_tokens,
                    )
                    run.actions_proposed += len(planning.plan.actions)
                    for action, outcome, detail in DreamActionExecutor().execute(
                        DreamActionContext(agent_id, user_id, self.memory_repository), planning.plan.actions, dream_settings.min_confidence
                    ):
                        action_index += 1
                        self.dream_repository.save_action_log(DreamActionLog(
                            run_id=run.run_id, index=action_index, action_type=action.type, block_name=action.block_name,
                            line_number=action.line_number, content_preview=redact(action.content)[0], reason=action.reason,
                            confidence=action.confidence, outcome=outcome, detail=detail,
                            session_ref=f"{session.conversation_id}:{session.ended_at.isoformat()}",
                        ))
                        # `no_op` is an audited planner decision, not a memory write.
                        # It must not consume the advisory action budget for the next session,
                        # but still needs its own bucket so proposed == executed + skipped + no_op.
                        if outcome == DreamActionOutcome.EXECUTED and action.type.value == "no_op":
                            run.actions_no_op += 1
                        elif outcome == DreamActionOutcome.EXECUTED:
                            run.actions_executed += 1
                        else:
                            run.actions_skipped += 1
                run.sessions_dreamed += 1
                run.longest_session_chunks = max(run.longest_session_chunks, len(chunks))
                cursor.last_session_ended_at = session.ended_at
                cursor.last_run_id = run.run_id
                cursor.sessions_dreamed += 1
                self.dream_repository.save_cursor(cursor)
                if run.actions_executed > dream_settings.soft_actions_per_run:
                    run.budget_overshoot_actions = run.actions_executed - dream_settings.soft_actions_per_run
                self.dream_repository.save_run(run)
            if window.mode == "backfill" and not run.sessions_remaining:
                cursor.backfill_completed = True
                self.dream_repository.save_cursor(cursor)
            run.budget_overshoot_chunks = max(0, run.chunks_planned - dream_settings.soft_chunks_per_run)
            return self._finish(run, DreamRunStatus.PARTIAL if run.sessions_remaining else DreamRunStatus.SUCCEEDED)
        except CancelledError:
            self._finish(run, DreamRunStatus.FAILED, "Dream worker cancelled before the run completed")
            raise
        except Exception as exc:
            return self._finish(run, DreamRunStatus.FAILED, str(exc))
        finally:
            # A transient error here must not replace the try block's real return value or
            # exception. The lease is harmless to leak: it self-expires, and the periodic
            # reaper (DreamRepository.fail_stale_runs) corrects the DreamRun row either way.
            try:
                self.dream_repository.release_run_lease(agent_id, user_id, run.run_id)
            except Exception:
                pass

    @staticmethod
    def _at_budget(run: DreamRun, dream_settings: DreamSettings) -> bool:
        return any((
            run.sessions_dreamed >= dream_settings.soft_sessions_per_run,
            run.chunks_planned >= dream_settings.soft_chunks_per_run,
            run.actions_executed >= dream_settings.soft_actions_per_run,
        ))

    def _finish(self, run: DreamRun, status: DreamRunStatus, error: str | None = None) -> DreamRun:
        run.status, run.error, run.completed_at = status, error, datetime.now(timezone.utc)
        return self.dream_repository.save_run(run)

    def _record_usage(
        self, owner_email: str, agent_id: str, model_name: str, prompt_tokens: int, completion_tokens: int
    ) -> None:
        if not prompt_tokens and not completion_tokens:
            return
        try:
            self.token_usage_service.record_usage(
                owner_email=owner_email, agent_id=agent_id, llm_model=model_name,
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            )
        except Exception:
            pass


def get_dream_service() -> DreamService:
    return DreamService()
