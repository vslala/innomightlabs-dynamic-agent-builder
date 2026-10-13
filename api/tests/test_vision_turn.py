"""A real memgpt turn: is `read_image` offered exactly when the conversation holds an image, and does the agent see the image tag?"""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.agentic_loop import TurnComplete
from src.agents.architectures.krishna_memgpt import KrishnaMemGPTArchitecture
from src.agents.models import Agent
from src.conversations.models import Conversation
from src.memory.snapshot import CoreMemorySnapshot
from src.messages.models import ImageAnalysis, Message
from src.skills.models import ActorKind
from src.vision.models import VisionSettings
from src.vision.repository import VisionSettingsRepository
from src.vision.uploads import ImageUploadService
from tests.mock_data import account_for, agent_fields, conversation_fields
from tests.vision_support import create_media_bucket, enable_vision, png_bytes

OWNER = "owner@example.com"


class FakeMessageRepository:
    def __init__(self, messages: list[Message] | None = None) -> None:
        self.messages = messages or []

    def save(self, message: Message) -> Message:
        self.messages.append(message)
        return message

    def find_by_conversation(self, conversation_id: str) -> list[Message]:
        return [m for m in self.messages if m.conversation_id == conversation_id]


class FakeProviderSettingsRepository:
    def find_by_provider(self, account_id: str, provider_name: str) -> Any:
        return type("ProviderSettings", (), {"encrypted_credentials": "encrypted"})()


class NoSkills:
    def list_usable(self, agent_id: str, actor_kind: ActorKind) -> list:
        return []


async def no_credentials(**kwargs: Any) -> dict:
    return {}


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    async def capture_loop(**kwargs: Any):
        seen.update(kwargs)
        yield TurnComplete(full_text="")

    monkeypatch.setattr("src.agents.architectures.krishna_memgpt.run_agentic_tool_loop", capture_loop)
    monkeypatch.setattr("src.agents.provider_session.get_llm_provider", lambda name: object())
    monkeypatch.setattr("src.agents.provider_session.load_provider_credentials", no_credentials)
    return seen


def _agent() -> Agent:
    return Agent(
        agent_name="Vision",
        agent_architecture="krishna-memgpt",
        agent_provider="Bedrock",
        agent_persona="Helpful",
        **agent_fields(OWNER),
    )


def _architecture(history: list[Message] | None = None) -> KrishnaMemGPTArchitecture:
    architecture = KrishnaMemGPTArchitecture()
    architecture.message_repo = FakeMessageRepository(history)  # type: ignore[assignment]
    architecture.provider_settings_repo = FakeProviderSettingsRepository()  # type: ignore[assignment]
    architecture.skill_runtime = NoSkills()  # type: ignore[assignment]
    architecture._get_linked_kb_ids = lambda agent: []  # type: ignore[method-assign]
    architecture._load_core_memory_snapshot = lambda agent_id, user_id: CoreMemorySnapshot(block_defs=[], blocks={})  # type: ignore[method-assign]
    return architecture


async def _turn(architecture: KrishnaMemGPTArchitecture, agent: Agent, conversation: Conversation, **kwargs: Any) -> None:
    async for _ in architecture.handle_message(
        agent=agent,
        conversation=conversation,
        user_message=kwargs.pop("user_message", "hello"),
        owner_email=OWNER,
        actor_email=OWNER,
        actor_id=OWNER,
        actor_kind=ActorKind.OWNER,
        **kwargs,
    ):
        pass


def _tool_names(captured: dict[str, Any]) -> list[str]:
    return [tool["name"] for tool in captured["tools"]]


def _conversation(agent: Agent) -> Conversation:
    return Conversation(title="Images", agent_id=agent.agent_id, **conversation_fields(OWNER))


def _enable_for_owner() -> None:
    enable_vision(account_id=account_for(OWNER), provider="Bedrock", model="claude-3-haiku")


def _uploaded_image(agent: Agent, conversation: Conversation):
    create_media_bucket()
    service = ImageUploadService()
    upload = service.store(
        agent=agent, conversation_id=conversation.conversation_id, uploaded_by=OWNER, filename="error.png", raw=png_bytes()
    )
    return service.attach(
        agent=agent, conversation_id=conversation.conversation_id, actor_id=OWNER, image_ids=[upload.image_id]
    )


async def test_read_image_is_offered_for_a_message_with_an_image(dynamodb_table, captured) -> None:
    _enable_for_owner()
    agent = _agent()
    conversation = _conversation(agent)
    images = _uploaded_image(agent, conversation)
    architecture = _architecture()

    await _turn(architecture, agent, conversation, user_message="What is this?", images=images)

    assert "read_image" in _tool_names(captured)
    saved = architecture.message_repo.find_by_conversation(conversation.conversation_id)[0]  # type: ignore[attr-defined]
    assert saved.image_attachments == images
    history = captured["context"][-1]["content"]
    assert f'<attached_image id="{images[0].image_id}" filename="error.png" size="40x30">' in history
    assert "Not described yet. Call read_image with this id to see it." in history


async def test_a_conversation_without_images_never_carries_the_tool(dynamodb_table, captured) -> None:
    _enable_for_owner()
    agent = _agent()

    await _turn(_architecture(), agent, _conversation(agent))

    assert "read_image" not in _tool_names(captured)


async def test_an_image_from_an_earlier_message_keeps_the_tool_on_later_text_turns(dynamodb_table, captured) -> None:
    _enable_for_owner()
    agent = _agent()
    conversation = _conversation(agent)
    images = _uploaded_image(agent, conversation)
    images[0].analysis = ImageAnalysis(description="A red dialog saying Payment failed.", provider_name="Bedrock", model_name="m")
    earlier = Message(conversation_id=conversation.conversation_id, role="user", content="look", image_attachments=images)

    await _turn(_architecture([earlier]), agent, conversation, user_message="and now?")

    assert "read_image" in _tool_names(captured)
    assert "Description: A red dialog saying Payment failed." in captured["context"][1]["content"]


async def test_turning_the_feature_off_removes_the_tool_but_not_the_descriptions(dynamodb_table, captured) -> None:
    _enable_for_owner()
    agent = _agent()
    conversation = _conversation(agent)
    images = _uploaded_image(agent, conversation)
    images[0].analysis = ImageAnalysis(description="A red dialog.", provider_name="Bedrock", model_name="m")
    earlier = Message(conversation_id=conversation.conversation_id, role="user", content="look", image_attachments=images)
    VisionSettingsRepository().save(VisionSettings(account_id=account_for(OWNER), enabled=False))

    await _turn(_architecture([earlier]), agent, conversation, user_message="and now?")

    assert "read_image" not in _tool_names(captured)
    assert "Description: A red dialog." in captured["context"][1]["content"]


async def test_the_tool_state_covers_images_outside_the_context_window(dynamodb_table, captured) -> None:
    """An old image that has fallen out of the window is still one `read_image` may open."""
    _enable_for_owner()
    agent = _agent()
    conversation = _conversation(agent)
    images = _uploaded_image(agent, conversation)
    old = Message(conversation_id=conversation.conversation_id, role="user", content="look", image_attachments=images)

    await _turn(_architecture([old]), agent, conversation, user_message="x " * 20_000)

    assert captured["state"].images.keys() == {images[0].image_id}
