from __future__ import annotations

import pytest

from src.scheduler.models import ScheduleTargetType
from src.scheduler.service import SchedulerService, SchedulerValidationError
from src.scheduler.targets import TARGET_VALIDATORS


@pytest.mark.parametrize(
    ("target_type", "target", "message"),
    [
        (
            ScheduleTargetType.AGENT_MESSAGE,
            {"message": "Check in"},
            "Agent message schedules require agent_id",
        ),
        (
            ScheduleTargetType.AGENT_MESSAGE,
            {"agent_id": "agent-1"},
            "Agent message schedules require message",
        ),
        (
            ScheduleTargetType.AUTOMATION_RUN,
            {"input": {}},
            "Automation schedules require automation_id",
        ),
        (
            ScheduleTargetType.AUTOMATION_RUN,
            {"automation_id": "automation-1", "input": "invalid"},
            "Automation schedule input must be an object",
        ),
    ],
)
def test_target_validator_registry_preserves_existing_error_messages(
    target_type: ScheduleTargetType,
    target: dict[str, object],
    message: str,
):
    with pytest.raises(ValueError, match=f"^{message}$"):
        TARGET_VALIDATORS[target_type].validate(target)


def test_dream_run_target_requires_agent_id():
    with pytest.raises(ValueError, match="^Dream schedules require agent_id$"):
        TARGET_VALIDATORS[ScheduleTargetType.DREAM_RUN].validate({"user_id": "user@example.com"})


def test_dream_run_target_allows_owner_default_user_id():
    TARGET_VALIDATORS[ScheduleTargetType.DREAM_RUN].validate({"agent_id": "agent-1"})


def test_scheduler_service_reports_unsupported_target_type():
    service = object.__new__(SchedulerService)

    with pytest.raises(
        SchedulerValidationError,
        match="^Unsupported schedule target type: unsupported$",
    ):
        service._validate_target("unsupported", {})
