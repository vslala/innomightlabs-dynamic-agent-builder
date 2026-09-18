from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast

from src.agents.models import Agent
from src.conversations.models import Conversation
from src.dream.models import DreamAction, DreamActionType, DreamCursor, DreamPlan, DreamRunStatus, DreamSettings
from src.dream.planner import DreamPlanningResult
from src.dream.service import DreamService
from src.memory.models import CoreMemory, MemoryBlockDefinition
from src.messages.models import Message


OWNER = "owner@example.com"
AGENT_ID = "agent-1"


class FakeDreamRepository:
    def __init__(self, settings: DreamSettings) -> None:
        self.settings = settings
        self.cursor: DreamCursor | None = None
        self.runs = []
        self.logs = []
        self.lease_available = True
        self.released_lease_run_ids = []

    def try_acquire_run_lease(self, agent_id, user_id, run_id, lease_seconds):
        return self.lease_available

    def renew_run_lease(self, agent_id, user_id, run_id, lease_seconds):
        return True

    def release_run_lease(self, agent_id, user_id, run_id):
        self.released_lease_run_ids.append(run_id)

    def find_settings(self, user_email: str):
        return self.settings

    def find_cursor(self, agent_id: str, user_id: str):
        return self.cursor

    def save_cursor(self, cursor: DreamCursor):
        self.cursor = cursor.model_copy(deep=True)
        return cursor

    def save_run(self, run):
        self.runs.append(run.model_copy(deep=True))
        return run

    def save_action_log(self, log):
        self.logs.append(log)
        return log


class FakeMemoryRepository:
    def __init__(self) -> None:
        self.definition = MemoryBlockDefinition(
            agent_id=AGENT_ID, user_id=OWNER, block_name="human", description="User facts"
        )
        self.memory = CoreMemory(agent_id=AGENT_ID, user_id=OWNER, block_name="human")

    def initialize_default_blocks(self, agent_id: str, user_id: str):
        pass

    def get_block_definitions(self, agent_id: str, user_id: str):
        return [self.definition]

    def get_block_definition(self, agent_id: str, user_id: str, block_name: str):
        return self.definition if block_name == "human" else None

    def get_all_core_memories(self, agent_id: str, user_id: str):
        return [self.memory]

    def get_core_memory(self, agent_id: str, user_id: str, block_name: str):
        return self.memory if block_name == "human" else None

    def save_core_memory(self, memory: CoreMemory):
        memory.word_count = memory.compute_word_count()
        self.memory = memory
        return memory

    def line_exists(self, agent_id: str, user_id: str, block_name: str, content: str):
        return next((index + 1 for index, line in enumerate(self.memory.lines) if line == content), None)


class FakeConversationRepository:
    def __init__(self, conversation: Conversation) -> None:
        self.conversation = conversation

    def find_all_by_user(self, owner_email: str):
        return [self.conversation]


class FakeMessageRepository:
    def __init__(self, conversation_id: str, messages: list[Message]) -> None:
        self.conversation_id = conversation_id
        self.messages = messages

    def has_messages_after(self, conversation_id: str, after: datetime):
        return any(message.created_at > after for message in self.messages)

    def find_by_conversation_paginated(self, conversation_id: str, limit: int, cursor):
        return self.messages, None, False


class FakeAgentRepository:
    def find_agent_by_id(self, agent_id: str, owner_email: str):
        return Agent(
            agent_id=AGENT_ID, agent_name="Dreamer", agent_architecture="krishna-memgpt",
            agent_provider="test", agent_persona="Helpful", created_by=OWNER, session_timeout_minutes=60,
        )


class FakeProviderSettingsRepository:
    def find_by_provider(self, owner_email: str, provider_name: str):
        return SimpleNamespace()


class PlannedActions:
    def __init__(self, results: list[DreamPlanningResult | Exception]) -> None:
        self.results = results
        self.calls = 0

    async def plan(self, **kwargs):
        result = self.results[self.calls]
        self.calls += 1
        if isinstance(result, Exception):
            raise result
        return result


def action(content: str = "durable fact") -> DreamAction:
    return DreamAction(
        type=DreamActionType.APPEND_CORE, block_name="human", content=content,
        reason="Durable preference", confidence=1.0,
    )


def result(*actions: DreamAction, summary: str = "summary") -> DreamPlanningResult:
    return DreamPlanningResult(plan=DreamPlan(actions=list(actions), session_summary=summary), prompt_tokens=1, completion_tokens=1)


def no_op() -> DreamAction:
    return DreamAction(type=DreamActionType.NO_OP, reason="No durable memory change", confidence=1.0)


def build_service(repository, memory, planner, messages: list[Message]) -> DreamService:
    conversation = Conversation(
        conversation_id="conversation-1", title="Dream test", agent_id=AGENT_ID, created_by=OWNER
    )
    return DreamService(
        dream_repository=cast(Any, repository),
        memory_repository=cast(Any, memory),
        conversation_repository=cast(Any, FakeConversationRepository(conversation)),
        message_repository=cast(Any, FakeMessageRepository(conversation.conversation_id, messages)),
        agent_repository=cast(Any, FakeAgentRepository()),
        provider_settings_repository=cast(Any, FakeProviderSettingsRepository()),
        planner=cast(Any, planner),
        token_usage_service=cast(Any, SimpleNamespace(record_usage=lambda **kwargs: None)),
    )


def stub_provider_access(monkeypatch) -> None:
    async def load_credentials(**kwargs):
        return {"token": "test"}

    monkeypatch.setattr("src.dream.service.load_provider_credentials", load_credentials)
    monkeypatch.setattr("src.dream.service.get_llm_provider", lambda provider_name: object())


def closed_messages(*, two_sessions: bool = False) -> list[Message]:
    started = datetime.now(timezone.utc) - timedelta(hours=4)
    minutes = [0, 1, 122] if two_sessions else [0, 1]
    return [
        Message(
            message_id=f"message-{index}", conversation_id="conversation-1", role="user",
            content="one two three", created_at=started + timedelta(minutes=offset),
        )
        for index, offset in enumerate(minutes)
    ]


async def test_action_budget_is_checked_between_sessions_after_finishing_current_session(monkeypatch):
    stub_provider_access(monkeypatch)
    monkeypatch.setattr("src.dream.service.app_settings.dream_chunk_max_words", 3)
    monkeypatch.setattr("src.dream.service.app_settings.dream_window_overlap_words", 1)
    repository = FakeDreamRepository(
        DreamSettings(
            user_email=OWNER, enabled=True, provider_name="test", model_name="test-model",
            soft_actions_per_run=1,
        )
    )
    memory = FakeMemoryRepository()
    planner = PlannedActions([result(action("first")), result(action("second"))])
    service = build_service(repository, memory, planner, closed_messages(two_sessions=True))

    run = await service.dream(agent_id=AGENT_ID, user_id=OWNER, owner_email=OWNER)

    assert run.status == DreamRunStatus.PARTIAL
    assert run.sessions_dreamed == 1
    assert run.sessions_remaining == 1
    assert run.actions_executed == 2
    assert run.budget_overshoot_actions == 1
    assert memory.memory.lines == ["first", "second"]
    assert repository.cursor is not None
    assert repository.cursor.sessions_dreamed == 1


async def test_no_op_is_audited_without_consuming_action_budget(monkeypatch):
    stub_provider_access(monkeypatch)
    repository = FakeDreamRepository(
        DreamSettings(
            user_email=OWNER, enabled=True, provider_name="test", model_name="test-model",
            soft_actions_per_run=1,
        )
    )
    memory = FakeMemoryRepository()
    service = build_service(repository, memory, PlannedActions([result(no_op())]), closed_messages())

    run = await service.dream(agent_id=AGENT_ID, user_id=OWNER, owner_email=OWNER)

    assert run.status == DreamRunStatus.SUCCEEDED
    assert run.actions_proposed == 1
    assert run.actions_executed == 0
    assert run.actions_skipped == 0
    assert run.actions_no_op == 1
    assert run.actions_proposed == run.actions_executed + run.actions_skipped + run.actions_no_op
    assert len(repository.logs) == 1
    assert repository.logs[0].action_type == DreamActionType.NO_OP
    assert repository.logs[0].outcome.value == "executed"


async def test_crash_before_session_completion_leaves_cursor_unadvanced_and_retry_replays_session(monkeypatch):
    stub_provider_access(monkeypatch)
    monkeypatch.setattr("src.dream.service.app_settings.dream_chunk_max_words", 3)
    monkeypatch.setattr("src.dream.service.app_settings.dream_window_overlap_words", 1)
    messages = closed_messages()
    repository = FakeDreamRepository(DreamSettings(user_email=OWNER, enabled=True, provider_name="test", model_name="test-model"))
    memory = FakeMemoryRepository()
    failed_attempt = build_service(
        repository, memory, PlannedActions([result(action()), RuntimeError("planner crashed")]), messages
    )

    failed_run = await failed_attempt.dream(agent_id=AGENT_ID, user_id=OWNER, owner_email=OWNER)

    assert failed_run.status == DreamRunStatus.FAILED
    assert failed_run.error == "planner crashed"
    assert repository.cursor is None
    assert memory.memory.lines == ["durable fact"]

    retry = build_service(repository, memory, PlannedActions([result(action()), result()]), messages)
    retried_run = await retry.dream(agent_id=AGENT_ID, user_id=OWNER, owner_email=OWNER)

    assert retried_run.status == DreamRunStatus.SUCCEEDED
    assert repository.cursor is not None
    assert repository.cursor.last_session_ended_at == messages[-1].created_at
    assert memory.memory.lines == ["durable fact"]
