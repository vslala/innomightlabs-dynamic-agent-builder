from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast

from src.agents.models import Agent
from src.conversations.models import Conversation
from src.dream.models import DreamCursor, DreamPlan, DreamRunStatus, DreamSettings
from src.dream.planner import DreamPlanningResult
from src.dream.service import DreamService
from src.memory.models import CoreMemory, MemoryBlockDefinition
from src.messages.models import Message


OWNER = "owner@example.com"
AGENT_ID = "agent-1"
USER_ID = OWNER


class FakeDreamRepository:
    def __init__(self, settings: DreamSettings, cursor: DreamCursor | None = None) -> None:
        self.settings = settings
        self.cursor = cursor
        self.runs = []
        self.action_logs = []

    def find_settings(self, user_email: str) -> DreamSettings | None:
        assert user_email == OWNER
        return self.settings

    def find_cursor(self, agent_id: str, user_id: str) -> DreamCursor | None:
        assert (agent_id, user_id) == (AGENT_ID, USER_ID)
        return self.cursor

    def save_cursor(self, cursor: DreamCursor) -> DreamCursor:
        self.cursor = cursor.model_copy(deep=True)
        return cursor

    def save_run(self, run):
        self.runs.append(run.model_copy(deep=True))
        return run

    def save_action_log(self, action_log):
        self.action_logs.append(action_log)
        return action_log


class FakeMemoryRepository:
    def __init__(self) -> None:
        self.initialized = False
        self.definitions = [
            MemoryBlockDefinition(
                agent_id=AGENT_ID, user_id=USER_ID, block_name="human", description="User facts"
            )
        ]
        self.memories: dict[str, CoreMemory] = {}

    def initialize_default_blocks(self, agent_id: str, user_id: str) -> None:
        self.initialized = True

    def get_block_definitions(self, agent_id: str, user_id: str):
        return self.definitions

    def get_block_definition(self, agent_id: str, user_id: str, block_name: str):
        return next((item for item in self.definitions if item.block_name == block_name), None)

    def get_all_core_memories(self, agent_id: str, user_id: str):
        return list(self.memories.values())

    def get_core_memory(self, agent_id: str, user_id: str, block_name: str):
        return self.memories.get(block_name)

    def save_core_memory(self, memory: CoreMemory) -> CoreMemory:
        memory.word_count = memory.compute_word_count()
        self.memories[memory.block_name] = memory
        return memory

    def line_exists(self, agent_id: str, user_id: str, block_name: str, content: str):
        memory = self.memories.get(block_name)
        if memory is None:
            return None
        return next((index + 1 for index, line in enumerate(memory.lines) if line == content), None)

    def insert_archival(self, agent_id: str, user_id: str, content: str):
        return SimpleNamespace(content=content), True


class FakeConversationRepository:
    def __init__(self, conversations) -> None:
        self.conversations = conversations

    def find_all_by_user(self, owner_email: str):
        assert owner_email == OWNER
        return self.conversations


class FakeMessageRepository:
    def __init__(self, messages_by_conversation: dict[str, list[Message]]) -> None:
        self.messages_by_conversation = messages_by_conversation

    def has_messages_after(self, conversation_id: str, after: datetime) -> bool:
        return any(message.created_at > after for message in self.messages_by_conversation[conversation_id])

    def find_by_conversation_paginated(self, conversation_id: str, limit: int, cursor):
        assert cursor is None
        return self.messages_by_conversation[conversation_id], None, False


class FakeAgentRepository:
    def __init__(self, agent: Agent | None) -> None:
        self.agent = agent

    def find_agent_by_id(self, agent_id: str, owner_email: str):
        assert (agent_id, owner_email) == (AGENT_ID, OWNER)
        return self.agent


class FakeProviderSettingsRepository:
    def find_by_provider(self, owner_email: str, provider_name: str):
        return SimpleNamespace(provider_name=provider_name)


class RecordingPlanner:
    def __init__(self, summaries: list[str]) -> None:
        self.summaries = summaries
        self.prior_summaries: list[str] = []

    async def plan(self, **kwargs):
        self.prior_summaries.append(kwargs["prior_summary"])
        return DreamPlanningResult(
            plan=DreamPlan(session_summary=self.summaries.pop(0)), prompt_tokens=3, completion_tokens=2
        )


class FakeTokenUsageService:
    def __init__(self) -> None:
        self.records = []

    def record_usage(self, **kwargs) -> None:
        self.records.append(kwargs)


def agent(architecture: str = "krishna-memgpt") -> Agent:
    return Agent(
        agent_id=AGENT_ID,
        agent_name="Dreamer",
        agent_architecture=architecture,
        agent_provider="test",
        agent_persona="Helpful",
        created_by=OWNER,
    )


def settings(**overrides) -> DreamSettings:
    values: dict[str, Any] = {
        "user_email": OWNER, "enabled": True, "provider_name": "test", "model_name": "test-model"
    }
    values.update(overrides)
    return DreamSettings(**values)


def conversation_and_messages(*, message_contents: list[str], gap_minutes: int = 1):
    started = datetime.now(timezone.utc) - timedelta(hours=3)
    conversation = Conversation(
        conversation_id="conversation-1", title="Dream test", agent_id=AGENT_ID, created_by=OWNER
    )
    messages = [
        Message(
            message_id=f"message-{index}", conversation_id=conversation.conversation_id,
            role="user", content=content, created_at=started + timedelta(minutes=index * gap_minutes),
        )
        for index, content in enumerate(message_contents)
    ]
    return conversation, messages


def stub_provider_access(monkeypatch) -> None:
    async def load_credentials(**kwargs):
        return {"token": "test"}

    monkeypatch.setattr("src.dream.service.load_provider_credentials", load_credentials)
    monkeypatch.setattr("src.dream.service.get_llm_provider", lambda provider_name: object())


def service_for(
    repository: FakeDreamRepository,
    *,
    agent_value: Agent | None = None,
    conversations=None,
    messages_by_conversation=None,
    planner=None,
    memory_repository=None,
    token_usage_service=None,
) -> DreamService:
    return DreamService(
        dream_repository=cast(Any, repository),
        memory_repository=cast(Any, memory_repository or FakeMemoryRepository()),
        conversation_repository=cast(Any, FakeConversationRepository(conversations or [])),
        message_repository=cast(Any, FakeMessageRepository(messages_by_conversation or {})),
        agent_repository=cast(Any, FakeAgentRepository(agent_value if agent_value is not None else agent())),
        provider_settings_repository=cast(Any, FakeProviderSettingsRepository()),
        planner=cast(Any, planner or RecordingPlanner([""])),
        token_usage_service=cast(Any, token_usage_service or FakeTokenUsageService()),
    )


async def test_dream_skips_when_disabled_without_initializing_memory():
    repository = FakeDreamRepository(settings(enabled=False, provider_name=None, model_name=None))
    memory_repository = FakeMemoryRepository()
    service = service_for(repository, memory_repository=memory_repository)

    run = await service.dream(agent_id=AGENT_ID, user_id=USER_ID, owner_email=OWNER)

    assert run.status == DreamRunStatus.SKIPPED
    assert run.error == "dreaming is disabled"
    assert not memory_repository.initialized


async def test_dream_skips_when_no_closed_sessions_exist():
    repository = FakeDreamRepository(settings())
    service = service_for(repository)

    run = await service.dream(agent_id=AGENT_ID, user_id=USER_ID, owner_email=OWNER)

    assert run.status == DreamRunStatus.SKIPPED
    assert run.error == "no_new_sessions"
    assert run.sessions_considered == 0


async def test_dream_skips_agents_without_memgpt_core_memory():
    repository = FakeDreamRepository(settings())
    memory_repository = FakeMemoryRepository()
    service = service_for(repository, agent_value=agent("krishna-mini"), memory_repository=memory_repository)

    run = await service.dream(agent_id=AGENT_ID, user_id=USER_ID, owner_email=OWNER)

    assert run.status == DreamRunStatus.SKIPPED
    assert run.error == "agent does not support core memory"
    assert not memory_repository.initialized


async def test_dream_carries_prior_summary_across_chunks_and_advances_cursor(monkeypatch):
    stub_provider_access(monkeypatch)
    monkeypatch.setattr("src.dream.service.app_settings.dream_chunk_max_words", 3)
    monkeypatch.setattr("src.dream.service.app_settings.dream_window_overlap_words", 1)
    conversation, messages = conversation_and_messages(message_contents=["one two three", "four five six"])
    repository = FakeDreamRepository(settings())
    planner = RecordingPlanner(["first chunk summary", "complete session summary"])
    usage = FakeTokenUsageService()
    service = service_for(
        repository,
        conversations=[conversation],
        messages_by_conversation={conversation.conversation_id: messages},
        planner=planner,
        token_usage_service=usage,
    )

    run = await service.dream(agent_id=AGENT_ID, user_id=USER_ID, owner_email=OWNER)

    assert run.status == DreamRunStatus.SUCCEEDED
    assert run.mode == "backfill"
    assert run.chunks_planned == 2
    assert planner.prior_summaries == ["", "first chunk summary"]
    assert repository.cursor is not None
    assert repository.cursor.last_session_ended_at == messages[-1].created_at
    assert repository.cursor.sessions_dreamed == 1
    assert repository.cursor.backfill_completed is True
    assert len(usage.records) == 2
