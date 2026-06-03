from __future__ import annotations
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.automations.models import AutomationStatus, CreateAutomationRequest, UpdateAutomationRequest
from src.automations.repository import AutomationRepository
from src.automations.service import AutomationService
from src.conversations.models import Conversation
from src.conversations.repository import ConversationRepository
from src.scheduler.cron import (
    ScheduleExpression,
    ScheduleExpressionError,
    next_run_at,
)
from src.scheduler.dispatcher import SchedulerDispatcher
from src.scheduler.models import (
    CreateScheduleRequest,
    Schedule,
    ScheduleRun,
    ScheduleRunStatus,
    ScheduleStatus,
    ScheduleTargetType,
)
from src.scheduler.repository import ScheduleRunAlreadyExists, SchedulerRepository
from src.scheduler.runtime import SchedulerRuntime
from src.scheduler.service import SchedulerService
from tests.mock_data import TEST_USER_EMAIL


class FakeSchedulerBackend:
    def __init__(self):
        self.upserts: list[str] = []
        self.pauses: list[str] = []
        self.resumes: list[str] = []
        self.deletes: list[str] = []

    def upsert(self, schedule: Schedule) -> None:
        self.upserts.append(schedule.schedule_id)

    def delete(self, schedule: Schedule) -> None:
        self.deletes.append(schedule.schedule_id)

    def pause(self, schedule: Schedule) -> None:
        self.pauses.append(schedule.schedule_id)

    def resume(self, schedule: Schedule) -> None:
        self.resumes.append(schedule.schedule_id)


class FakeScheduleTargetExecutor:
    async def execute(self, schedule: Schedule, scheduled_for: datetime) -> dict:
        return {"schedule_id": schedule.schedule_id, "scheduled_for": scheduled_for.isoformat()}


def test_cron_validation_and_next_run():
    expression = ScheduleExpression("*/5 * * * *", "UTC")

    assert next_run_at(expression, datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)) == datetime(
        2026, 1, 1, 0, 5, tzinfo=timezone.utc
    )


def test_cron_rejects_invalid_shape():
    with pytest.raises(ScheduleExpressionError):
        next_run_at(ScheduleExpression("* * * *", "UTC"))


def test_scheduler_repository_saves_schedule_lookup_items(dynamodb_table):
    repository = SchedulerRepository()
    schedule = Schedule(
        owner_email=TEST_USER_EMAIL,
        name="Wake agent",
        cron_expression="*/5 * * * *",
        target_type=ScheduleTargetType.AGENT_MESSAGE,
        target={
            "agent_id": "agent-1",
            "conversation_id": "conversation-1",
            "message": "Check in",
        },
        created_by=TEST_USER_EMAIL,
        next_run_at=datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
    )

    repository.save_schedule(schedule)

    assert repository.find_schedule(TEST_USER_EMAIL, schedule.schedule_id) is not None
    assert dynamodb_table.get_item(
        Key={"pk": "Agent#agent-1", "sk": f"Schedule#{schedule.schedule_id}"}
    ).get("Item")
    assert dynamodb_table.get_item(
        Key={"pk": "Conversation#conversation-1", "sk": f"Schedule#{schedule.schedule_id}"}
    ).get("Item")


def test_scheduler_repository_updates_schedule_with_same_lookup_key(dynamodb_table):
    repository = SchedulerRepository()
    schedule = Schedule(
        schedule_id="schedule-1",
        owner_email=TEST_USER_EMAIL,
        name="Initial",
        cron_expression="*/5 * * * *",
        target_type=ScheduleTargetType.AUTOMATION_RUN,
        target={"automation_id": "automation-1", "trigger_id": "trigger-1", "input": {}},
        source_type="automation_trigger",
        source_ref={"automation_id": "automation-1", "trigger_id": "trigger-1"},
        created_by=TEST_USER_EMAIL,
        next_run_at=datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
    )
    repository.save_schedule(schedule)

    schedule.name = "Updated"
    schedule.target = {
        "automation_id": "automation-1",
        "trigger_id": "trigger-1",
        "input": {"source": "updated"},
    }

    repository.save_schedule(schedule)

    saved = repository.find_schedule(TEST_USER_EMAIL, "schedule-1")
    assert saved is not None
    assert saved.name == "Updated"
    assert saved.target["input"] == {"source": "updated"}


def test_scheduler_repository_lists_active_schedules_from_gsi(dynamodb_table):
    repository = SchedulerRepository()
    active_schedule = Schedule(
        owner_email=TEST_USER_EMAIL,
        name="Active",
        cron_expression="*/5 * * * *",
        target_type=ScheduleTargetType.AGENT_MESSAGE,
        target={"agent_id": "agent-1", "message": "Check in"},
        created_by=TEST_USER_EMAIL,
        next_run_at=datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
    )
    paused_schedule = Schedule(
        owner_email=TEST_USER_EMAIL,
        name="Paused",
        cron_expression="*/5 * * * *",
        target_type=ScheduleTargetType.AGENT_MESSAGE,
        target={"agent_id": "agent-1", "message": "Check in"},
        created_by=TEST_USER_EMAIL,
        next_run_at=None,
    )
    paused_schedule.status = ScheduleStatus.PAUSED

    repository.save_schedule(active_schedule)
    repository.save_schedule(paused_schedule)

    assert [schedule.schedule_id for schedule in repository.list_active_schedules()] == [
        active_schedule.schedule_id
    ]


def test_scheduler_repository_run_idempotency(dynamodb_table):
    repository = SchedulerRepository()
    scheduled_for = datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc)
    run = ScheduleRun(
        run_id=ScheduleRun.deterministic_run_id("schedule-1", scheduled_for),
        schedule_id="schedule-1",
        owner_email=TEST_USER_EMAIL,
        scheduled_for=scheduled_for,
        status=ScheduleRunStatus.RUNNING,
        target_type=ScheduleTargetType.AUTOMATION_RUN,
    )

    repository.save_run_once(run)

    with pytest.raises(ScheduleRunAlreadyExists):
        repository.save_run_once(run)


def test_scheduler_service_uses_backend_and_repository(dynamodb_table):
    backend = FakeSchedulerBackend()
    service = SchedulerService(repository=SchedulerRepository(), backend=backend)

    schedule = service.create_schedule(
        CreateScheduleRequest(
            name="Run automation",
            cron_expression="*/5 * * * *",
            target_type=ScheduleTargetType.AUTOMATION_RUN,
            target={"automation_id": "automation-1", "input": {"task": "cleanup"}},
        ),
        owner_email=TEST_USER_EMAIL,
        created_by=TEST_USER_EMAIL,
    )

    assert backend.upserts == [schedule.schedule_id]
    assert service.get_schedule(schedule.schedule_id, TEST_USER_EMAIL).target["automation_id"] == "automation-1"


@pytest.mark.asyncio
async def test_scheduler_runtime_registers_active_schedules_on_start(dynamodb_table):
    repository = SchedulerRepository()
    schedule = Schedule(
        owner_email=TEST_USER_EMAIL,
        name="Active",
        cron_expression="*/5 * * * *",
        target_type=ScheduleTargetType.AGENT_MESSAGE,
        target={"agent_id": "agent-1", "message": "Check in"},
        created_by=TEST_USER_EMAIL,
        next_run_at=datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
    )
    repository.save_schedule(schedule)
    runtime = SchedulerRuntime(repository=repository)

    await runtime.start()
    try:
        assert runtime.scheduler.get_job(schedule.schedule_id) is not None
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_scheduler_dispatcher_records_duplicate_as_skipped(dynamodb_table):
    backend = FakeSchedulerBackend()
    repository = SchedulerRepository()
    service = SchedulerService(repository=repository, backend=backend)
    schedule = service.create_schedule(
        CreateScheduleRequest(
            name="Run automation",
            cron_expression="*/5 * * * *",
            target_type=ScheduleTargetType.AUTOMATION_RUN,
            target={"automation_id": "automation-1", "input": {}},
        ),
        owner_email=TEST_USER_EMAIL,
        created_by=TEST_USER_EMAIL,
    )
    dispatcher = SchedulerDispatcher(
        repository=repository,
        service=service,
        executors={ScheduleTargetType.AUTOMATION_RUN: FakeScheduleTargetExecutor()},
    )
    scheduled_for = datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc)

    first = await dispatcher.dispatch(
        schedule_id=schedule.schedule_id,
        owner_email=TEST_USER_EMAIL,
        scheduled_for=scheduled_for,
    )
    second = await dispatcher.dispatch(
        schedule_id=schedule.schedule_id,
        owner_email=TEST_USER_EMAIL,
        scheduled_for=scheduled_for,
    )

    assert first.status == ScheduleRunStatus.SUCCEEDED
    assert second.status == ScheduleRunStatus.SKIPPED
    assert second.output["reason"] == "duplicate_dispatch"


@pytest.mark.asyncio
async def test_scheduler_dispatcher_invokes_agent_message_target(dynamodb_table, monkeypatch):
    backend = FakeSchedulerBackend()
    repository = SchedulerRepository()
    service = SchedulerService(repository=repository, backend=backend)
    agent = Agent(
        agent_name="Scheduler Agent",
        agent_architecture="krishna-mini",
        agent_provider="openai",
        agent_persona="Helpful",
        created_by=TEST_USER_EMAIL,
    )
    AgentRepository().save(agent)
    conversation = Conversation(
        title="Scheduled conversation",
        agent_id=agent.agent_id,
        created_by=TEST_USER_EMAIL,
    )
    ConversationRepository().save(conversation)
    schedule = service.create_schedule(
        CreateScheduleRequest(
            name="Wake agent",
            cron_expression="*/5 * * * *",
            target_type=ScheduleTargetType.AGENT_MESSAGE,
            target={
                "agent_id": agent.agent_id,
                "conversation_id": conversation.conversation_id,
                "message": "Run the scheduled task",
                "actor_email": TEST_USER_EMAIL,
                "actor_id": "user-1",
            },
        ),
        owner_email=TEST_USER_EMAIL,
        created_by=TEST_USER_EMAIL,
    )
    captured: dict[str, object] = {}

    class FakeArchitecture:
        async def handle_message_buffered(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                success=True,
                error=None,
                response_text="scheduled response",
                user_message_id="user-message-1",
                assistant_message_id="assistant-message-1",
                events=[],
            )

    monkeypatch.setattr(
        "src.scheduler.executors.get_agent_architecture",
        lambda architecture_name: FakeArchitecture(),
    )
    assert schedule.next_run_at is not None
    dispatcher = SchedulerDispatcher(repository=repository, service=service)

    run = await dispatcher.dispatch(
        schedule_id=schedule.schedule_id,
        owner_email=TEST_USER_EMAIL,
        scheduled_for=schedule.next_run_at,
    )

    assert run.status == ScheduleRunStatus.SUCCEEDED
    assert run.output["response_text"] == "scheduled response"
    assert run.output["message_ids"] == {
        "user_message_id": "user-message-1",
        "assistant_message_id": "assistant-message-1",
    }
    assert captured["agent"].agent_id == agent.agent_id
    assert captured["conversation"].conversation_id == conversation.conversation_id
    assert captured["user_message"] == "Run the scheduled task"
    assert captured["owner_email"] == TEST_USER_EMAIL
    assert captured["actor_email"] == TEST_USER_EMAIL
    assert captured["actor_id"] == "user-1"


@pytest.mark.asyncio
async def test_scheduler_dispatcher_invokes_automation_run_target(dynamodb_table):
    backend = FakeSchedulerBackend()
    repository = SchedulerRepository()
    scheduler_service = SchedulerService(repository=repository, backend=backend)
    automation_service = AutomationService(repo=AutomationRepository())
    automation_graph = automation_service.create_automation(
        CreateAutomationRequest(title="Scheduled automation"),
        TEST_USER_EMAIL,
    )
    automation_service.update_automation(
        automation_graph.automation.automation_id,
        UpdateAutomationRequest(status=AutomationStatus.ACTIVE),
        TEST_USER_EMAIL,
    )
    schedule = scheduler_service.create_schedule(
        CreateScheduleRequest(
            name="Run automation",
            cron_expression="*/5 * * * *",
            target_type=ScheduleTargetType.AUTOMATION_RUN,
            target={
                "automation_id": automation_graph.automation.automation_id,
                "input": {"source": "scheduler"},
            },
        ),
        owner_email=TEST_USER_EMAIL,
        created_by=TEST_USER_EMAIL,
    )
    assert schedule.next_run_at is not None
    dispatcher = SchedulerDispatcher(repository=repository, service=scheduler_service)

    run = await dispatcher.dispatch(
        schedule_id=schedule.schedule_id,
        owner_email=TEST_USER_EMAIL,
        scheduled_for=schedule.next_run_at,
    )

    assert run.status == ScheduleRunStatus.SUCCEEDED
    assert run.output["automation_id"] == automation_graph.automation.automation_id
    assert run.output["status"] == "succeeded"
    automation_run = AutomationRepository().find_run_by_id(
        run.output["automation_run_id"],
        TEST_USER_EMAIL,
    )
    assert automation_run is not None
    assert automation_run.context["input"] == {"source": "scheduler"}
    assert automation_run.context["trigger"]["type"] == "schedule"
    assert automation_run.context["trigger"]["schedule_id"] == schedule.schedule_id
