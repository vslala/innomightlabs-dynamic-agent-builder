"""One-time schedules: a reminder runs once at `run_at` and completes, instead of repeating every year."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from src.scheduler.dispatcher import SchedulerDispatcher
from src.scheduler.models import CreateScheduleRequest, Schedule, ScheduleStatus, ScheduleTargetType
from src.scheduler.repository import SchedulerRepository
from src.scheduler.runtime import SchedulerRuntime
from src.scheduler.service import SchedulerService, SchedulerValidationError
from src.scheduler.timing import moment
from src.skills.scheduler import actions as scheduler_skill
from tests.mock_data import TEST_USER_EMAIL
from tests.test_scheduler import FakeSchedulerBackend, FakeScheduleTargetExecutor

TARGET = {"automation_id": "automation-1", "input": {}}


def soon(minutes: int = 30) -> datetime:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).replace(microsecond=0)


def service(backend: FakeSchedulerBackend | None = None) -> SchedulerService:
    return SchedulerService(repository=SchedulerRepository(), backend=backend or FakeSchedulerBackend())


def once(svc: SchedulerService, run_at: datetime, **extra) -> Schedule:
    return svc.create_schedule(
        CreateScheduleRequest(
            name="Remind me", run_at=run_at, target_type=ScheduleTargetType.AUTOMATION_RUN, target=TARGET, **extra
        ),
        owner_email=TEST_USER_EMAIL,
        created_by=TEST_USER_EMAIL,
    )


# --- Creating one --------------------------------------------------------------------------------


def test_a_one_time_schedule_is_due_at_its_moment(dynamodb_table):
    run_at = soon()
    schedule = once(service(), run_at)
    assert (schedule.status, schedule.cron_expression, schedule.next_run_at) == (ScheduleStatus.ACTIVE, "", run_at)
    assert schedule.schedule_id in {item.schedule_id for item in SchedulerRepository().list_active_schedules()}


def test_a_time_without_an_offset_is_read_in_the_schedules_timezone(dynamodb_table):
    schedule = once(service(), datetime(2099, 7, 1, 9, 0), timezone="Europe/London")
    assert moment(schedule) == datetime(2099, 7, 1, 8, 0, tzinfo=timezone.utc)  # BST is UTC+1


@pytest.mark.parametrize(
    "request_fields, message",
    [
        ({"run_at": datetime(2020, 1, 1, tzinfo=timezone.utc)}, "run_at is in the past"),
        ({"run_at": datetime(2099, 1, 1, tzinfo=timezone.utc), "cron_expression": "0 9 * * *"}, "not both"),
        ({}, "Give a cron_expression"),
    ],
)
def test_a_schedule_runs_once_or_repeats_never_both_or_neither(dynamodb_table, request_fields, message):
    with pytest.raises(SchedulerValidationError, match=message):
        service().create_schedule(
            CreateScheduleRequest(
                name="Remind me", target_type=ScheduleTargetType.AUTOMATION_RUN, target=TARGET, **request_fields
            ),
            owner_email=TEST_USER_EMAIL,
            created_by=TEST_USER_EMAIL,
        )


# --- Running it ----------------------------------------------------------------------------------


class FailingExecutor:
    async def execute(self, schedule: Schedule, scheduled_for: datetime) -> dict:
        raise RuntimeError("agent unreachable")


@pytest.mark.parametrize("executor", [FakeScheduleTargetExecutor(), FailingExecutor()], ids=["succeeds", "fails"])
async def test_after_its_run_a_one_time_schedule_is_completed(dynamodb_table, executor):
    backend = FakeSchedulerBackend()
    svc = service(backend)
    schedule = once(svc, soon())
    dispatcher = SchedulerDispatcher(
        repository=svc.repository, service=svc, executors={ScheduleTargetType.AUTOMATION_RUN: executor}
    )
    await dispatcher.dispatch(schedule_id=schedule.schedule_id, owner_email=TEST_USER_EMAIL, scheduled_for=soon())

    done = svc.get_schedule(schedule.schedule_id, TEST_USER_EMAIL)
    assert (done.status, done.next_run_at) == (ScheduleStatus.COMPLETED, None) and done.last_run_at
    assert schedule.schedule_id in backend.deletes  # taken off the process clock
    assert schedule.schedule_id not in {item.schedule_id for item in svc.repository.list_active_schedules()}

    # It never runs again, even if the clock fires once more, and can't be resumed.
    again = await dispatcher.dispatch(
        schedule_id=schedule.schedule_id, owner_email=TEST_USER_EMAIL, scheduled_for=soon(60)
    )
    assert again.output == {"reason": "schedule_completed"}
    with pytest.raises(SchedulerValidationError, match="already ran once"):
        svc.resume_schedule(schedule.schedule_id, TEST_USER_EMAIL)


async def test_a_recurring_schedule_moves_on_even_when_a_run_fails(dynamodb_table):
    svc = service()
    schedule = svc.create_schedule(
        CreateScheduleRequest(
            name="Hourly", cron_expression="0 * * * *", target_type=ScheduleTargetType.AUTOMATION_RUN, target=TARGET
        ),
        owner_email=TEST_USER_EMAIL,
        created_by=TEST_USER_EMAIL,
    )
    fired = datetime(2099, 1, 1, 10, 0, tzinfo=timezone.utc)
    dispatcher = SchedulerDispatcher(
        repository=svc.repository, service=svc, executors={ScheduleTargetType.AUTOMATION_RUN: FailingExecutor()}
    )
    await dispatcher.dispatch(schedule_id=schedule.schedule_id, owner_email=TEST_USER_EMAIL, scheduled_for=fired)
    after = svc.get_schedule(schedule.schedule_id, TEST_USER_EMAIL)
    assert after.status == ScheduleStatus.ACTIVE
    assert after.next_run_at == datetime(2099, 1, 1, 11, 0, tzinfo=timezone.utc)


# --- On the process clock ------------------------------------------------------------------------


def test_the_runtime_uses_a_date_trigger_once_and_a_cron_trigger_to_repeat():
    runtime = SchedulerRuntime(repository=object())  # type: ignore[arg-type]
    base = dict(owner_email=TEST_USER_EMAIL, name="x", target_type=ScheduleTargetType.AUTOMATION_RUN, created_by="x")
    runtime.upsert(Schedule(schedule_id="once", run_at=soon(), **base))
    runtime.upsert(Schedule(schedule_id="repeat", cron_expression="0 9 * * 1", **base))
    assert isinstance(runtime.scheduler.get_job("once").trigger, DateTrigger)
    assert isinstance(runtime.scheduler.get_job("repeat").trigger, CronTrigger)


def test_a_wake_up_missed_while_the_server_was_down_runs_when_it_is_back():
    runtime = SchedulerRuntime(repository=object())  # type: ignore[arg-type]
    missed = datetime.now(timezone.utc) - timedelta(hours=2)
    runtime.upsert(Schedule(
        schedule_id="missed", run_at=missed, owner_email=TEST_USER_EMAIL, name="x",
        target_type=ScheduleTargetType.AUTOMATION_RUN, created_by="x",
    ))
    trigger = runtime.scheduler.get_job("missed").trigger
    assert trigger.run_date > datetime.now(timezone.utc)


# --- The skill -----------------------------------------------------------------------------------


@pytest.fixture
def skill_context(dynamodb_table, monkeypatch):
    backend = FakeSchedulerBackend()
    monkeypatch.setattr(scheduler_skill, "SchedulerService", lambda: SchedulerService(backend=backend))
    return {"owner_email": TEST_USER_EMAIL, "agent_id": "agent-1", "conversation_id": "conv-1"}


async def test_the_skill_saves_a_one_time_wake_up(skill_context):
    result = await scheduler_skill.create_or_update(
        {"name": "Follow up", "message": "Ask how the demo went", "run_at": soon().isoformat()}, {}, skill_context
    )
    assert result["schedule"]["run_at"] and result["schedule"]["cron_expression"] == ""
    assert "runs once" in result["message"]


@pytest.mark.parametrize(
    "timing",
    [{}, {"run_at": "2099-01-01T09:00:00Z", "cron_expression": "0 9 * * *"}, {"run_at": "tomorrow at 9"}],
    ids=["neither", "both", "not iso"],
)
async def test_the_skill_says_what_it_needs(skill_context, timing):
    with pytest.raises(ValueError, match="run_at"):
        await scheduler_skill.create_or_update({"name": "Follow up", "message": "Hi", **timing}, {}, skill_context)
