"""Schedule target validation rules."""

from __future__ import annotations

from typing import Any, Protocol

from src.scheduler.models import ScheduleTargetType


class ScheduleTargetValidator(Protocol):
    """Validates the target payload for one schedule target type."""

    target_type: ScheduleTargetType

    def validate(self, target: dict[str, Any]) -> None: ...


class AgentMessageTargetValidator:
    target_type = ScheduleTargetType.AGENT_MESSAGE

    def validate(self, target: dict[str, Any]) -> None:
        if not str(target.get("agent_id") or "").strip():
            raise ValueError("Agent message schedules require agent_id")
        if not str(target.get("message") or "").strip():
            raise ValueError("Agent message schedules require message")


class AutomationRunTargetValidator:
    target_type = ScheduleTargetType.AUTOMATION_RUN

    def validate(self, target: dict[str, Any]) -> None:
        if not str(target.get("automation_id") or "").strip():
            raise ValueError("Automation schedules require automation_id")
        raw_input = target.get("input", {})
        if raw_input is not None and not isinstance(raw_input, dict):
            raise ValueError("Automation schedule input must be an object")


class DreamRunTargetValidator:
    target_type = ScheduleTargetType.DREAM_RUN

    def validate(self, target: dict[str, Any]) -> None:
        if not str(target.get("agent_id") or "").strip():
            raise ValueError("Dream schedules require agent_id")


TARGET_VALIDATORS: dict[ScheduleTargetType, ScheduleTargetValidator] = {
    ScheduleTargetType.AGENT_MESSAGE: AgentMessageTargetValidator(),
    ScheduleTargetType.AUTOMATION_RUN: AutomationRunTargetValidator(),
    ScheduleTargetType.DREAM_RUN: DreamRunTargetValidator(),
}
