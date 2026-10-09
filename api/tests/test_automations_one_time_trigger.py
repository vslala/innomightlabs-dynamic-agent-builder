"""A schedule trigger can start an automation once, at `run_at`, as well as repeatedly on a cron expression."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.automations.models import (
    AutomationStatus,
    AutomationTriggerType,
    CreateAutomationRequest,
    UpdateAutomationRequest,
    UpdateAutomationTriggerRequest,
)
from src.automations.repository import AutomationRepository
from src.automations.service import AutomationService
from src.automations.triggers.models import ScheduleTriggerConfig
from src.automations.triggers.schemas import build_schedule_trigger_form
from src.automations.triggers.service import AutomationTriggerLifecycleService
from src.scheduler.dispatcher import SchedulerDispatcher
from src.scheduler.models import ScheduleStatus, ScheduleTargetType
from src.scheduler.repository import SchedulerRepository
from src.scheduler.service import SchedulerService
from tests.mock_data import TEST_USER_EMAIL
from tests.test_scheduler import FakeSchedulerBackend, FakeScheduleTargetExecutor


def soon(minutes: int = 30) -> datetime:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).replace(microsecond=0)


# --- The config ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "config",
    [{"cron_expression": "0 9 * * *", "run_at": "2099-01-01T09:00:00Z"}, {"cron_expression": "", "run_at": ""}],
    ids=["both", "neither"],
)
def test_a_trigger_repeats_or_runs_once(config):
    with pytest.raises(ValueError, match="not both"):
        ScheduleTriggerConfig.model_validate(config)


def test_the_form_field_left_empty_is_simply_unset():
    repeating = ScheduleTriggerConfig.model_validate({"cron_expression": " 0 9 * * 1 ", "run_at": ""})
    once = ScheduleTriggerConfig.model_validate({"cron_expression": "", "run_at": "2099-01-01T09:00"})
    assert (repeating.cron_expression, repeating.run_at) == ("0 9 * * 1", None)
    assert once.run_at == datetime(2099, 1, 1, 9, 0)


def test_the_form_offers_both_ways():
    names = [field.name for field in build_schedule_trigger_form([]).form_inputs]
    assert names.index("run_at") == names.index("cron_expression") + 1


# --- Its life ------------------------------------------------------------------------------------


@pytest.fixture
def services(dynamodb_table):
    schedules = SchedulerService(repository=SchedulerRepository(), backend=FakeSchedulerBackend())
    automations = AutomationService(
        repo=AutomationRepository(), trigger_lifecycle=AutomationTriggerLifecycleService(scheduler_service=schedules)
    )
    return automations, schedules


def one_time(automations: AutomationService, run_at: datetime) -> tuple[str, str]:
    graph = automations.create_automation(CreateAutomationRequest(title="Launch announcement"), TEST_USER_EMAIL)
    automation_id, trigger = graph.automation.automation_id, graph.triggers[0]
    automations.update_trigger(
        automation_id,
        trigger.trigger_id,
        UpdateAutomationTriggerRequest(
            type=AutomationTriggerType.SCHEDULE,
            name="Launch day",
            config={"run_at": run_at.isoformat(), "cron_expression": "", "timezone": "UTC"},
        ),
        TEST_USER_EMAIL,
    )
    return automation_id, trigger.trigger_id


def status(automations: AutomationService, automation_id: str, value: AutomationStatus) -> None:
    automations.update_automation(automation_id, UpdateAutomationRequest(status=value), TEST_USER_EMAIL)


async def test_a_one_time_trigger_runs_once_and_survives_being_switched_off_and_on(services):
    automations, schedules = services
    run_at = soon()
    automation_id, trigger_id = one_time(automations, run_at)
    status(automations, automation_id, AutomationStatus.ACTIVE)

    schedule_id = AutomationTriggerLifecycleService.schedule_id_for(automation_id, trigger_id)
    schedule = schedules.get_schedule(schedule_id, TEST_USER_EMAIL)
    assert (schedule.status, schedule.run_at, schedule.next_run_at) == (ScheduleStatus.ACTIVE, run_at, run_at)

    dispatcher = SchedulerDispatcher(
        repository=schedules.repository,
        service=schedules,
        executors={ScheduleTargetType.AUTOMATION_RUN: FakeScheduleTargetExecutor()},
    )
    await dispatcher.dispatch(schedule_id=schedule_id, owner_email=TEST_USER_EMAIL, scheduled_for=run_at)
    assert schedules.get_schedule(schedule_id, TEST_USER_EMAIL).status == ScheduleStatus.COMPLETED

    # Switching the automation off and on again neither fails (the moment has passed) nor runs it again.
    status(automations, automation_id, AutomationStatus.DISABLED)
    status(automations, automation_id, AutomationStatus.ACTIVE)
    assert schedules.get_schedule(schedule_id, TEST_USER_EMAIL).status == ScheduleStatus.COMPLETED

    # A new moment schedules it again.
    again = soon(90)
    automations.update_trigger(
        automation_id,
        trigger_id,
        UpdateAutomationTriggerRequest(config={"run_at": again.isoformat(), "cron_expression": "", "timezone": "UTC"}),
        TEST_USER_EMAIL,
    )
    rescheduled = schedules.get_schedule(schedule_id, TEST_USER_EMAIL)
    assert (rescheduled.status, rescheduled.next_run_at) == (ScheduleStatus.ACTIVE, again)


def test_a_moment_already_past_is_refused_when_the_automation_is_switched_on(services):
    """A draft's schedule is saved paused, and checked for timing when the automation goes active."""
    automations, _ = services
    automation_id, trigger_id = one_time(automations, soon())
    automations.update_trigger(
        automation_id,
        trigger_id,
        UpdateAutomationTriggerRequest(
            config={"run_at": "2020-01-01T09:00:00+00:00", "cron_expression": "", "timezone": "UTC"}
        ),
        TEST_USER_EMAIL,
    )
    with pytest.raises(ValueError, match="in the past"):
        status(automations, automation_id, AutomationStatus.ACTIVE)


def test_the_api_says_why_it_wont_switch_on(test_client, auth_headers):
    created = test_client.post("/automations", json={"title": "Launch"}, headers=auth_headers).json()
    automation_id = created["automation"]["automation_id"]
    trigger = created["triggers"][0]
    response = test_client.patch(
        f"/automations/{automation_id}/triggers/{trigger['trigger_id']}",
        json={"type": "schedule", "config": {"run_at": "2020-01-01T09:00:00Z", "cron_expression": "", "timezone": "UTC"}},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text

    response = test_client.patch(f"/automations/{automation_id}", json={"status": "active"}, headers=auth_headers)
    assert response.status_code == 422
    assert "in the past" in response.json()["detail"]
