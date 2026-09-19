import json

from src.agents.agentic_loop import AgenticLoopEvent
from src.agents.architectures.krishna_memgpt import KrishnaMemGPTArchitecture
from src.agents.models import Agent
from src.agents.runtime_state import AgentTurnState
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


async def fake_mcp_tool_call_loop(**kwargs):
    yield AgenticLoopEvent(
        kind="tool_call_start",
        payload={
            "tool_call_id": "tooluse_mcp",
            "tool_name": "call_mcp_tool",
            "tool_args": {
                "mcp_id": "atlassian",
                "tool_name": "searchJiraIssuesUsingJql",
                "arguments": {"jql": "project = KAN"},
            },
        },
    )
    yield AgenticLoopEvent(
        kind="tool_call_result",
        payload={
            "tool_call_id": "tooluse_mcp",
            "tool_name": "call_mcp_tool",
            "result": "[]",
            "success": True,
        },
    )
    yield AgenticLoopEvent(kind="text", payload={"content": "no issues found"})
    yield AgenticLoopEvent(kind="complete", payload={"full_text": "no issues found"})


async def fake_prompt_refresh_loop(**kwargs):
    yield AgenticLoopEvent(kind="prompt_refresh_needed", payload={})
    yield AgenticLoopEvent(kind="complete", payload={"full_text": ""})


async def fake_empty_tool_turn_loop(**kwargs):
    yield AgenticLoopEvent(
        kind="tool_call_start",
        payload={
            "tool_call_id": "tooluse_empty",
            "tool_name": "search_docs",
            "tool_args": {"query": "pricing"},
        },
    )
    yield AgenticLoopEvent(
        kind="tool_call_result",
        payload={
            "tool_call_id": "tooluse_empty",
            "tool_name": "search_docs",
            "result": "pricing result",
            "success": True,
        },
    )
    yield AgenticLoopEvent(kind="complete", payload={"full_text": ""})


async def fake_canvas_tool_loop(**kwargs):
    yield AgenticLoopEvent(
        kind="tool_call_start",
        payload={
            "tool_call_id": "tooluse_canvas",
            "tool_name": "render_canvas",
            "tool_args": {"title": "Revenue"},
        },
    )
    yield AgenticLoopEvent(
        kind="tool_call_result",
        payload={
            "tool_call_id": "tooluse_canvas",
            "tool_name": "render_canvas",
            "result": json.dumps(
                {
                    "ok": True,
                    "type": "canvas_artifact",
                    "artifact_id": "artifact-1",
                    "title": "Revenue",
                    "caption": "Q1 revenue",
                    "mime_type": "text/html",
                }
            ),
            "success": True,
        },
    )
    yield AgenticLoopEvent(kind="text", payload={"content": "Here is your chart"})
    yield AgenticLoopEvent(kind="complete", payload={"full_text": "Here is your chart"})


async def fake_load_provider_credentials(**kwargs):
    return {}


async def test_krishna_memgpt_saves_tool_call_as_system_message(monkeypatch):
    monkeypatch.setattr(
        "src.agents.architectures.krishna_memgpt.run_agentic_tool_loop",
        fake_run_agentic_tool_loop,
    )
    monkeypatch.setattr(
        "src.agents.provider_session.get_llm_provider",
        lambda provider_name: object(),
    )
    monkeypatch.setattr(
        "src.agents.provider_session.load_provider_credentials",
        fake_load_provider_credentials,
    )

    architecture = KrishnaMemGPTArchitecture()
    message_repo = FakeMessageRepository()
    architecture.message_repo = message_repo
    architecture.provider_settings_repo = FakeProviderSettingsRepository()
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


async def test_krishna_memgpt_unwraps_call_mcp_tool_for_display(monkeypatch):
    monkeypatch.setattr(
        "src.agents.architectures.krishna_memgpt.run_agentic_tool_loop",
        fake_mcp_tool_call_loop,
    )
    monkeypatch.setattr(
        "src.agents.provider_session.get_llm_provider",
        lambda provider_name: object(),
    )
    monkeypatch.setattr(
        "src.agents.provider_session.load_provider_credentials",
        fake_load_provider_credentials,
    )

    architecture = KrishnaMemGPTArchitecture()
    architecture.message_repo = FakeMessageRepository()
    architecture.provider_settings_repo = FakeProviderSettingsRepository()
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
            user_message="Search Jira",
            owner_email="owner@example.com",
            actor_email="owner@example.com",
            actor_id="owner@example.com",
            attachments=[],
        )
    ]

    start_event = next(event for event in events if event.event_type == SSEEventType.TOOL_CALL_START)
    result_event = next(event for event in events if event.event_type == SSEEventType.TOOL_CALL_RESULT)

    # Raw wrapper values are preserved for audit/debug views.
    assert start_event.tool_name == "call_mcp_tool"
    assert start_event.tool_args == {
        "mcp_id": "atlassian",
        "tool_name": "searchJiraIssuesUsingJql",
        "arguments": {"jql": "project = KAN"},
    }
    # Display fields carry the unwrapped, real MCP tool identity.
    assert start_event.display_tool_name == "searchJiraIssuesUsingJql"
    assert start_event.display_tool_args == {"jql": "project = KAN"}

    assert result_event.tool_name == "call_mcp_tool"
    assert result_event.display_tool_name == "searchJiraIssuesUsingJql"
    assert result_event.display_tool_args == {"jql": "project = KAN"}


async def test_prompt_refresh_preserves_enabled_mcp_connections(monkeypatch):
    monkeypatch.setattr(
        "src.agents.architectures.krishna_memgpt.run_agentic_tool_loop",
        fake_prompt_refresh_loop,
    )
    monkeypatch.setattr(
        "src.agents.provider_session.get_llm_provider",
        lambda provider_name: object(),
    )
    monkeypatch.setattr(
        "src.agents.provider_session.load_provider_credentials",
        fake_load_provider_credentials,
    )

    architecture = KrishnaMemGPTArchitecture()
    architecture.message_repo = FakeMessageRepository()
    architecture.provider_settings_repo = FakeProviderSettingsRepository()
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


async def test_krishna_memgpt_empty_tool_turn_emits_and_persists_fallback(monkeypatch):
    monkeypatch.setattr(
        "src.agents.architectures.krishna_memgpt.run_agentic_tool_loop",
        fake_empty_tool_turn_loop,
    )
    monkeypatch.setattr(
        "src.agents.provider_session.get_llm_provider",
        lambda provider_name: object(),
    )
    monkeypatch.setattr(
        "src.agents.provider_session.load_provider_credentials",
        fake_load_provider_credentials,
    )

    architecture = KrishnaMemGPTArchitecture()
    message_repo = FakeMessageRepository()
    architecture.message_repo = message_repo
    architecture.provider_settings_repo = FakeProviderSettingsRepository()
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

    response_events = [
        event
        for event in events
        if event.event_type == SSEEventType.AGENT_RESPONSE_TO_USER
    ]

    assert not [event for event in events if event.event_type == SSEEventType.ERROR]
    assert len(response_events) == 1
    assert response_events[0].content
    assert "tools finished running" in response_events[0].content
    assert events[-2].event_type == SSEEventType.ASSISTANT_MESSAGE_SAVED
    assert events[-1].event_type == SSEEventType.STREAM_COMPLETE
    assert [message.role for message in message_repo.messages] == [
        "user",
        "system",
        "assistant",
    ]
    assert message_repo.messages[-1].content == response_events[0].content


async def test_krishna_memgpt_attaches_canvas_artifact_to_assistant_message(monkeypatch):
    monkeypatch.setattr(
        "src.agents.architectures.krishna_memgpt.run_agentic_tool_loop",
        fake_canvas_tool_loop,
    )
    monkeypatch.setattr(
        "src.agents.provider_session.get_llm_provider",
        lambda provider_name: object(),
    )
    monkeypatch.setattr(
        "src.agents.provider_session.load_provider_credentials",
        fake_load_provider_credentials,
    )
    monkeypatch.setattr(
        "src.agents.architectures.krishna_memgpt.settings.api_base_url",
        "https://api.example.com",
    )

    architecture = KrishnaMemGPTArchitecture()
    message_repo = FakeMessageRepository()
    architecture.message_repo = message_repo
    architecture.provider_settings_repo = FakeProviderSettingsRepository()
    architecture.skill_runtime = FakeSkillRuntime()
    architecture._get_linked_kb_ids = lambda agent_id: []
    architecture._ensure_memory_initialized = lambda agent_id, user_id: None
    architecture._load_core_memory_snapshot = lambda agent_id, user_id: object()
    architecture._check_capacity_warnings_from_snapshot = lambda snapshot: []
    architecture._build_system_prompt = lambda *args, **kwargs: "system prompt"

    agent = Agent(
        agent_name="Canvas Agent",
        agent_architecture="krishna-memgpt",
        agent_provider="Bedrock",
        agent_persona="Helpful",
        created_by="owner@example.com",
    )
    conversation = Conversation(
        title="Canvas",
        agent_id=agent.agent_id,
        created_by="owner@example.com",
    )

    events = [
        event
        async for event in architecture.handle_message(
            agent=agent,
            conversation=conversation,
            user_message="Chart Q1 revenue",
            owner_email="owner@example.com",
            actor_email="owner@example.com",
            actor_id="owner@example.com",
            attachments=[],
        )
    ]

    canvas_events = [event for event in events if event.event_type == SSEEventType.CANVAS_ARTIFACT_READY]
    assert len(canvas_events) == 1
    assert canvas_events[0].canvas_artifact_id == "artifact-1"
    assert canvas_events[0].canvas_title == "Revenue"
    assert canvas_events[0].canvas_caption == "Q1 revenue"
    assert canvas_events[0].canvas_content_url == "https://api.example.com/artifacts/artifact-1/content"

    assistant_messages = [message for message in message_repo.messages if message.role == "assistant"]
    assert len(assistant_messages) == 1
    assert len(assistant_messages[0].canvases) == 1
    assert assistant_messages[0].canvases[0].artifact_id == "artifact-1"
    assert assistant_messages[0].canvases[0].title == "Revenue"


def test_krishna_memgpt_builds_tool_definitions_from_command_registry():
    architecture = KrishnaMemGPTArchitecture()
    architecture.skill_runtime = FakeSkillRuntime()
    architecture.mcp_connector_service = FakeMCPConnectorService()

    state = AgentTurnState(
        owner_email="owner@example.com",
        actor_email="owner@example.com",
        actor_id="owner@example.com",
        conversation_id="conversation-1",
        agent_id="agent-1",
        provider_name="Bedrock",
        model_name="test-model",
        user_message="hello",
    )
    state.linked_kb_ids = ["kb-1"]
    state.enabled_skills = [object()]
    state.enabled_mcp_connections = [object()]

    registry = architecture._build_tool_registry()
    tool_names = {
        definition["name"]
        for definition in architecture._build_tool_definitions(state, registry)
    }

    assert "core_memory_append" in tool_names
    assert "knowledge_base_search" in tool_names
    assert "load_skill" in tool_names
    assert "execute_skill_action" in tool_names
    assert "list_mcp_tools" in tool_names
    assert "call_mcp_tool" in tool_names
