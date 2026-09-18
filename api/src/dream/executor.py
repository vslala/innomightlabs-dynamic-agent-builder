"""Scheduler target executor for nightly Dreams."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.config import settings
from src.dream.models import DreamRun, DreamRunStatus
from src.dream.service import DreamService
from src.scheduler.models import Schedule


class DreamScheduledExecutor:
    def __init__(self, service: DreamService | None = None) -> None:
        self.service = service or DreamService()

    async def execute(self, schedule: Schedule, scheduled_for: datetime) -> dict[str, Any]:
        agent_id = str(schedule.target.get("agent_id") or "").strip()
        if not agent_id:
            raise ValueError("Dream schedule target requires agent_id")
        user_id = str(schedule.target.get("user_id") or schedule.owner_email)
        if not settings.dream_enabled:
            return {
                "scheduled_for": scheduled_for.isoformat(), "agent_id": agent_id,
                "status": DreamRunStatus.SKIPPED.value, "mode": "daily",
                "sessions_dreamed": 0, "actions_executed": 0, "actions_skipped": 0,
                "error": "dreaming is globally disabled",
            }
        run = await self.service.dream(
            agent_id=agent_id, user_id=user_id, owner_email=schedule.owner_email, mode="daily"
        )
        if run.status == DreamRunStatus.FAILED:
            raise RuntimeError(run.error or "Dream run failed")
        return self._output(scheduled_for, agent_id, run)

    @staticmethod
    def _output(scheduled_for: datetime, agent_id: str, run: DreamRun) -> dict[str, Any]:
        return {
            "scheduled_for": scheduled_for.isoformat(), "agent_id": agent_id,
            "dream_run_id": run.run_id, "status": run.status.value, "mode": run.mode,
            "sessions_dreamed": run.sessions_dreamed, "actions_executed": run.actions_executed,
            "actions_skipped": run.actions_skipped, "error": run.error,
        }
