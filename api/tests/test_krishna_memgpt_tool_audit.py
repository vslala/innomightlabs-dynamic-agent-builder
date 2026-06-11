import json

from src.agents.agentic_loop import AgenticLoopEvent
from src.agents.architectures.krishna_memgpt import KrishnaMemGPTArchitecture
from src.agents.models import Agent
from src.agents.tool_audit import ToolCallAuditMessage
from src.conversations.models import Conversation
from src.llm.events import SSEEventType


class FakeMessageRepository:
    def __init__(self):
        self.messages = []

    def save(self, message):
        self.messages.append(message)
        return message

    def find_by_conversation(self, conversation_id):
        return [
            message
            for message in self.messages
            if message.conversation_id == conversation_id
        ]


class FakeProviderSettingsRepository:
    def find_by_provider(self, owner_email, provider_name):
        class FakeProviderSettings:
            encrypted_credentials = "encrypted"

        return FakeProviderSettings()


class FakeToolHandler:
    def set_conversation_context(self, conversation_id):
        pass

    def set_user_context(self, user_id):
        pass

    def set_knowledge_base_context(self, kb_ids):
        pass


class FakeSkillRuntime:
    def list_enabled(self, agent_id):
        return []


class FakeMCPConnectorService:
    def list_agent_connections(self, **kwargs):
        return ["mcp-connection"]


async def fake_run_agentic_tool_loop(**kwargs):
    yield AgenticLoopEvent(
        kind="tool_call_start",
        payload={
            "tool_call_id": "tooluse_1",
            "tool_name": "search_docs",
            "tool_args": {"query": "pricing"},
        },
    )
    yield AgenticLoopEvent(
        kind="tool_call_result",
        payload={
            "tool_call_id": "tooluse_1",
            "tool_name": "search_docs",
            "result": "pricing result",
            "success": True,
        },
    )
    yield AgenticLoopEvent(kind="text", payload={"content": "final answer"})
    yield AgenticLoopEvent(kind="complete", payload={"full_text": "final answer"})


async def fake_prompt_refresh_loop(**kwargs):
    yield AgenticLoopEvent(kind="prompt_refresh_needed", payload={})
    yield AgenticLoopEvent(kind="complete", payload={"full_text": ""})


async def test_krishna_memgpt_saves_tool_call_as_system_message(monkeypatch):
    monkeypatch.setattr(
        "src.agents.agentic_loop.run_agentic_tool_loop",
        fake_run_agentic_tool_loop,
    )
    monkeypatch.setattr(
        "src.agents.architectures.krishna_memgpt.get_llm_provider",
        lambda provider_name: object(),
    )
    monkeypatch.setattr(
        "src.agents.architectures.krishna_memgpt.decrypt",
        lambda encrypted_credentials: "{}",
    )

    architecture = KrishnaMemGPTArchitecture()
    message_repo = FakeMessageRepository()
    architecture.message_repo = message_repo
    architecture.provider_settings_repo = FakeProviderSettingsRepository()
    architecture.tool_handler = FakeToolHandler()
    architecture.skill_runtime = FakeSkillRuntime()
    architecture._get_linked_kb_ids = lambda agent_id: []
    architecture._ensure_memory_initialized = lambda agent_id, user_id: None
    architecture._load_core_memory_snapshot = lambda agent_id, user_id: object()
    architecture._check_capacity_warnings_from_snapshot = lambda snapshot: []
    architecture._build_system_prompt = lambda *args, **kwargs: "system prompt"

    agent = Agent(
        agent_name="Audit Agent",
        agent_architecture="krishna-memgpt",
        agent_provider="Bedrock",
        agent_persona="Helpful",
        created_by="owner@example.com",
    )
    conversation = Conversation(
        title="Audit",
        agent_id=agent.agent_id,
        created_by="owner@example.com",
    )

    events = [
        event
        async for event in architecture.handle_message(
            agent=agent,
            conversation=conversation,
            user_message="Run a search",
            owner_email="owner@example.com",
            actor_email="owner@example.com",
            actor_id="owner@example.com",
            attachments=[],
        )
    ]

    assert not [event for event in events if event.event_type == SSEEventType.ERROR]
    assert [event.event_type for event in events] == [
        SSEEventType.USER_MESSAGE_SAVED,
        SSEEventType.LIFECYCLE_NOTIFICATION,
        SSEEventType.LIFECYCLE_NOTIFICATION,
        SSEEventType.LIFECYCLE_NOTIFICATION,
        SSEEventType.LIFECYCLE_NOTIFICATION,
        SSEEventType.TOOL_CALL_START,
        SSEEventType.TOOL_CALL_RESULT,
        SSEEventType.AGENT_RESPONSE_TO_USER,
        SSEEventType.ASSISTANT_MESSAGE_SAVED,
        SSEEventType.STREAM_COMPLETE,
    ]
    assert events[0].message_id == message_repo.messages[0].message_id
    assert events[-2].message_id == message_repo.messages[-1].message_id
    assert events[-1].message_id is None
    assert [message.role for message in message_repo.messages] == [
        "user",
        "system",
        "assistant",
    ]

    audit_payload = json.loads(message_repo.messages[1].content)
    audit = ToolCallAuditMessage(**audit_payload)
    assert audit.tool_call_id == "tooluse_1"
    assert audit.sequence == 1
    assert audit.tool_name == "search_docs"
    assert audit.tool_args == {"query": "pricing"}
    assert audit.result == "pricing result"
    assert audit.success is True


async def test_prompt_refresh_preserves_enabled_mcp_connections(monkeypatch):
    monkeypatch.setattr(
        "src.agents.agentic_loop.run_agentic_tool_loop",
        fake_prompt_refresh_loop,
    )
    monkeypatch.setattr(
        "src.agents.architectures.krishna_memgpt.get_llm_provider",
        lambda provider_name: object(),
    )
    monkeypatch.setattr(
        "src.agents.architectures.krishna_memgpt.decrypt",
        lambda encrypted_credentials: "{}",
    )

    architecture = KrishnaMemGPTArchitecture()
    architecture.message_repo = FakeMessageRepository()
    architecture.provider_settings_repo = FakeProviderSettingsRepository()
    architecture.tool_handler = FakeToolHandler()
    architecture.skill_runtime = FakeSkillRuntime()
    architecture.mcp_connector_service = FakeMCPConnectorService()
    architecture._get_linked_kb_ids = lambda agent_id: []
    architecture._ensure_memory_initialized = lambda agent_id, user_id: None
    architecture._load_core_memory_snapshot = lambda agent_id, user_id: object()
    architecture._check_capacity_warnings_from_snapshot = lambda snapshot: []

    prompt_calls = []

    def fake_build_system_prompt(*args, **kwargs):
        prompt_calls.append(kwargs)
        return "system prompt"

    architecture._build_system_prompt = fake_build_system_prompt

    agent = Agent(
        agent_name="Audit Agent",
        agent_architecture="krishna-memgpt",
        agent_provider="Bedrock",
        agent_persona="Helpful",
        created_by="owner@example.com",
    )
    conversation = Conversation(
        title="Audit",
        agent_id=agent.agent_id,
        created_by="owner@example.com",
    )

    events = [
        event
        async for event in architecture.handle_message(
            agent=agent,
            conversation=conversation,
            user_message="Remember and then use Jira",
            owner_email="owner@example.com",
            actor_email="owner@example.com",
            actor_id="owner@example.com",
            attachments=[],
        )
    ]

    assert not [event for event in events if event.event_type == SSEEventType.ERROR]
    assert len(prompt_calls) == 2
    assert prompt_calls[0]["enabled_mcp_connections"] == ["mcp-connection"]
    assert prompt_calls[1]["enabled_mcp_connections"] == ["mcp-connection"]
