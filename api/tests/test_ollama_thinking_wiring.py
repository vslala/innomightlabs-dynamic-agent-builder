"""Confirms the per-agent Ollama thinking-mode choice actually reaches the
provider call in both agent architectures, not just the pure merge function."""

from src.agents.architectures.krishna_memgpt import KrishnaMemGPTArchitecture
from src.agents.architectures.krishna_mini import KrishnaMiniArchitecture
from src.agents.models import Agent
from src.conversations.models import Conversation


class FakeMessageRepository:
    def __init__(self):
        self.messages = []

    def save(self, message):
        self.messages.append(message)
        return message

    def find_by_conversation(self, conversation_id):
        return [m for m in self.messages if m.conversation_id == conversation_id]


class FakeProviderSettingsRepository:
    def find_by_provider(self, user_email, provider_name):
        class FakeProviderSettings:
            encrypted_credentials = "encrypted"

        return FakeProviderSettings()


class FakeSkillRuntime:
    def list_enabled(self, agent_id):
        return []


class FakeMCPConnectorService:
    def list_agent_connections(self, **kwargs):
        return []


class RecordingProvider:
    """Captures the credentials dict it was actually called with."""

    def __init__(self):
        self.received_credentials = None

    async def stream_response(self, messages, credentials, tools=None, model=None):
        self.received_credentials = credentials
        if False:
            yield None
        return


async def fake_load_provider_credentials(**kwargs):
    return {"endpoint_url": "http://ollama.test:11434"}


def _ollama_agent(thinking_mode) -> Agent:
    return Agent(
        agent_name="Ollama Agent",
        agent_architecture="krishna-memgpt",
        agent_provider="Ollama",
        agent_model="qwen3:8b",
        agent_persona="Helpful",
        agent_ollama_thinking=thinking_mode,
        created_by="owner@example.com",
    )


async def test_krishna_memgpt_forwards_the_agents_thinking_choice_to_the_provider(monkeypatch):
    recording_provider = RecordingProvider()
    monkeypatch.setattr(
        "src.agents.provider_session.get_llm_provider",
        lambda provider_name: recording_provider,
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
    architecture._build_system_prompt = lambda *args, **kwargs: "system prompt"

    agent = _ollama_agent("enabled")
    conversation = Conversation(title="T", agent_id=agent.agent_id, created_by="owner@example.com")

    events = [
        event
        async for event in architecture.handle_message(
            agent=agent,
            conversation=conversation,
            user_message="hi",
            owner_email="owner@example.com",
            actor_email="owner@example.com",
            actor_id="owner@example.com",
            attachments=[],
        )
    ]

    assert not [e for e in events if e.event_type.name == "ERROR"]
    assert recording_provider.received_credentials == {
        "endpoint_url": "http://ollama.test:11434",
        "think": True,
    }


async def test_krishna_memgpt_sends_no_think_key_when_the_agent_has_no_preference(monkeypatch):
    recording_provider = RecordingProvider()
    monkeypatch.setattr(
        "src.agents.provider_session.get_llm_provider",
        lambda provider_name: recording_provider,
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
    architecture._build_system_prompt = lambda *args, **kwargs: "system prompt"

    agent = _ollama_agent(None)
    conversation = Conversation(title="T", agent_id=agent.agent_id, created_by="owner@example.com")

    async for _ in architecture.handle_message(
        agent=agent,
        conversation=conversation,
        user_message="hi",
        owner_email="owner@example.com",
        actor_email="owner@example.com",
        actor_id="owner@example.com",
        attachments=[],
    ):
        pass

    assert "think" not in recording_provider.received_credentials


async def test_krishna_mini_forwards_the_agents_thinking_choice_to_the_provider(monkeypatch):
    recording_provider = RecordingProvider()
    monkeypatch.setattr(
        "src.agents.provider_session.get_llm_provider",
        lambda provider_name: recording_provider,
    )
    monkeypatch.setattr(
        "src.agents.provider_session.load_provider_credentials",
        fake_load_provider_credentials,
    )

    architecture = KrishnaMiniArchitecture()
    architecture.message_repo = FakeMessageRepository()
    architecture.provider_settings_repo = FakeProviderSettingsRepository()

    agent = _ollama_agent("disabled")
    agent.agent_architecture = "krishna-mini"
    conversation = Conversation(title="T", agent_id=agent.agent_id, created_by="owner@example.com")

    async for _ in architecture.handle_message(
        agent=agent,
        conversation=conversation,
        user_message="hi",
        owner_email="owner@example.com",
        actor_email="owner@example.com",
        actor_id="owner@example.com",
    ):
        pass

    assert recording_provider.received_credentials == {
        "endpoint_url": "http://ollama.test:11434",
        "think": False,
    }
