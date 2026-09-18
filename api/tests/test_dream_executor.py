from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.dream.executor import DreamScheduledExecutor
from src.dream.models import DreamRun, DreamRunStatus
from src.scheduler.models import Schedule, ScheduleTargetType
from tests.mock_data import TEST_USER_EMAIL


class FakeDreamService:
    def __init__(self, run: DreamRun) -> None:
        self.run = run
        self.calls: list[dict[str, str]] = []

    async def dream(self, **kwargs: str) -> DreamRun:
        self.calls.append(kwargs)
        return self.run


def _schedule(target: dict[str, str] | None = None) -> Schedule:
    return Schedule(
        schedule_id="dream-schedule",
        owner_email=TEST_USER_EMAIL,
        name="Nightly memory dream",
        cron_expression="0 3 * * *",
        target_type=ScheduleTargetType.DREAM_RUN,
        target={"agent_id": "missing-agent"} if target is None else target,
        created_by=TEST_USER_EMAIL,
    )


def _run(status: DreamRunStatus, *, error: str | None = None) -> DreamRun:
    return DreamRun(
        run_id="dream-run",
        agent_id="missing-agent",
        user_id=TEST_USER_EMAIL,
        owner_email=TEST_USER_EMAIL,
        status=status,
        error=error,
    )


@pytest.mark.asyncio
async def test_execute_missing_agent_is_reported_as_a_skipped_dream_run(monkeypatch: pytest.MonkeyPatch):
    service = FakeDreamService(_run(DreamRunStatus.SKIPPED, error="agent does not support core memory"))
    monkeypatch.setattr("src.dream.executor.settings", SimpleNamespace(dream_enabled=True))

    result = await DreamScheduledExecutor(service).execute(
        _schedule(), datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc)
    )

    assert result == {
        "scheduled_for": "2026-01-01T03:00:00+00:00",
        "agent_id": "missing-agent",
        "dream_run_id": "dream-run",
        "status": "skipped",
        "mode": "daily",
        "sessions_dreamed": 0,
        "actions_executed": 0,
        "actions_skipped": 0,
        "error": "agent does not support core memory",
    }
    assert service.calls == [{
        "agent_id": "missing-agent",
        "user_id": TEST_USER_EMAIL,
        "owner_email": TEST_USER_EMAIL,
        "mode": "daily",
    }]


@pytest.mark.asyncio
async def test_execute_raises_for_failed_dream_run(monkeypatch: pytest.MonkeyPatch):
    service = FakeDreamService(_run(DreamRunStatus.FAILED, error="provider unavailable"))
    monkeypatch.setattr("src.dream.executor.settings", SimpleNamespace(dream_enabled=True))

    with pytest.raises(RuntimeError, match="^provider unavailable$"):
        await DreamScheduledExecutor(service).execute(
            _schedule(), datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc)
        )


@pytest.mark.asyncio
async def test_execute_requires_an_agent_id():
    service = FakeDreamService(_run(DreamRunStatus.SUCCEEDED))

    with pytest.raises(ValueError, match="^Dream schedule target requires agent_id$"):
        await DreamScheduledExecutor(service).execute(
            _schedule({}), datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc)
        )

    assert service.calls == []
