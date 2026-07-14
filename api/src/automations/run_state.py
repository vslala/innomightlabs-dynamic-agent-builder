"""Automation run state transitions and heartbeat liveness."""

from datetime import datetime, timezone

from src.automations.models import AutomationRun, AutomationRunStatus
from src.automations.repository import AutomationRepository

AUTOMATION_RUN_DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 30 * 60
AUTOMATION_RUN_HEARTBEAT_INTERVAL_SECONDS = 60


class AutomationRunStateService:
    """Owns run lifecycle transitions and liveness metadata."""

    def __init__(self, repo: AutomationRepository):
        self.repo = repo

    def start(self, run: AutomationRun) -> AutomationRun:
        now = _utcnow()
        run.status = AutomationRunStatus.RUNNING
        run.started_at = run.started_at or now
        run.last_heartbeat_at = now
        run.heartbeat_timeout_seconds = (
            run.heartbeat_timeout_seconds or AUTOMATION_RUN_DEFAULT_HEARTBEAT_TIMEOUT_SECONDS
        )
        return self.repo.save_run(run)

    def heartbeat(
        self,
        run: AutomationRun,
        *,
        current_node_id: str | None = None,
        node_started: bool = False,
    ) -> AutomationRun:
        now = _utcnow()
        if run.status == AutomationRunStatus.PENDING:
            run.status = AutomationRunStatus.RUNNING
            run.started_at = run.started_at or now
        run.last_heartbeat_at = now
        if current_node_id is not None:
            run.current_node_id = current_node_id
            if node_started or run.current_node_started_at is None:
                run.current_node_started_at = now
        return self.repo.save_run(run)

    def complete_node(self, run: AutomationRun) -> AutomationRun:
        run.last_heartbeat_at = _utcnow()
        run.current_node_id = None
        run.current_node_started_at = None
        return self.repo.save_run(run)

    def succeed(self, run: AutomationRun) -> AutomationRun:
        now = _utcnow()
        run.status = AutomationRunStatus.SUCCEEDED
        run.error = None
        run.completed_at = now
        run.last_heartbeat_at = now
        run.current_node_id = None
        run.current_node_started_at = None
        return self.repo.save_run(run)

    def fail(self, run: AutomationRun, error: str | None) -> AutomationRun:
        now = _utcnow()
        run.status = AutomationRunStatus.FAILED
        run.error = error or "Automation run failed"
        run.completed_at = now
        run.last_heartbeat_at = now
        run.current_node_id = None
        run.current_node_started_at = None
        return self.repo.save_run(run)

    def is_stale(self, run: AutomationRun, now: datetime | None = None) -> bool:
        if run.status not in {AutomationRunStatus.PENDING, AutomationRunStatus.RUNNING}:
            return False
        reference_time = run.last_heartbeat_at or run.started_at or run.created_at
        elapsed_seconds = (_as_aware_utc(now or _utcnow()) - _as_aware_utc(reference_time)).total_seconds()
        timeout_seconds = run.heartbeat_timeout_seconds or AUTOMATION_RUN_DEFAULT_HEARTBEAT_TIMEOUT_SECONDS
        return elapsed_seconds > timeout_seconds

    def fail_if_stale(self, run: AutomationRun) -> AutomationRun:
        if not self.is_stale(run):
            return run
        current = f" while running node '{run.current_node_id}'" if run.current_node_id else ""
        return self.fail(
            run,
            (
                "Automation run heartbeat expired"
                f"{current}. The worker may have been interrupted; please retry the automation."
            ),
        )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
