"""Drawing through an agent: who draws, and the chat turn the drawing leaves behind.

The service runs for real against moto. Only the S3 storage and the vendor's drawing adapter are stand-ins, since
those are the external boundaries."""

import json

import pytest

from src.agents.image_generation.models import GenerateImageRequest
from src.agents.image_generation.service import AgentImageGenerationService, ImageGenerationNotSupportedError
from src.agents.image_generation.settings import ImageGenerationSettings, ImageGenerationSettingsRepository
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.conversations.models import Conversation
from src.conversations.repository import ConversationRepository
from src.crypto import encrypt
from src.llm.events import SSEEventType
from src.llm.images import GeneratedImageBytes, ImageGenerationStreamEvent
from src.messages.repositories import get_message_repository
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from tests.llm_doubles import use_provider
from tests.mock_data import TEST_USER_EMAIL, account_for, agent_fields, conversation_fields

ACCOUNT = account_for(TEST_USER_EMAIL)


class FakeStorage:
    def build_image_key(self, *, agent_id, conversation_id, message_id, extension):
        return f"agents/{agent_id}/conversations/{conversation_id}/messages/{message_id}/image.{extension}"

    def put_image(self, *, key, body, content_type):
        return None

    def presign_get_url(self, key):
        return f"https://signed.example/{key}?signature=test"


class FakeDrawing:
    """The vendor: draws one 256px PNG and remembers what it was asked."""

    def __init__(self):
        self.asked: dict = {}

    async def stream_generate(self, **kwargs):
        self.asked.update(kwargs)
        yield ImageGenerationStreamEvent(kind="generating")
        yield ImageGenerationStreamEvent(kind="image", image=GeneratedImageBytes(
            data=b"fake-image", output_format="png", mime_type="image/png", prompt=kwargs["prompt"],
            width=256, height=256,
        ))

    async def generate(self, **kwargs):
        self.asked.update(kwargs)
        return [GeneratedImageBytes(data=b"fake-image", output_format="png", mime_type="image/png",
                                    prompt=kwargs["prompt"])]


@pytest.fixture
def drawing(monkeypatch) -> FakeDrawing:
    """OpenAIAPI draws through the fake; every other provider keeps its real drawer."""
    fake = FakeDrawing()
    use_provider(monkeypatch, "OpenAIAPI", images=fake)
    return fake


@pytest.fixture
def service(dynamodb_table, drawing) -> AgentImageGenerationService:
    return AgentImageGenerationService(storage=FakeStorage())


def _provider_set_up(name: str) -> None:
    ProviderSettingsRepository().save(ProviderSettings(
        account_id=ACCOUNT, provider_name=name, encrypted_credentials=encrypt(json.dumps({"api_key": "sk-test"}))))


def _drawing_with(provider_name: str, model_name: str) -> None:
    _provider_set_up(provider_name)
    ImageGenerationSettingsRepository().save(ImageGenerationSettings(
        account_id=ACCOUNT, enabled=True, provider_name=provider_name, model_name=model_name))


def _agent_and_conversation(provider: str = "Anthropic") -> tuple[Agent, Conversation]:
    agent = AgentRepository().save(Agent(
        agent_name="Artist", agent_architecture="krishna-memgpt", agent_provider=provider, agent_model="claude-haiku",
        agent_persona="You draw.", **agent_fields(TEST_USER_EMAIL),
    ))
    conversation = ConversationRepository().save(Conversation(
        title="Pictures", agent_id=agent.agent_id, **conversation_fields(TEST_USER_EMAIL)))
    return agent, conversation


async def _skill_draws(service: AgentImageGenerationService, agent: Agent, conversation: Conversation) -> list:
    return [
        event
        async for event in service.stream_for_agent_turn(
            agent_id=agent.agent_id,
            conversation_id=conversation.conversation_id,
            actor_email=TEST_USER_EMAIL,
            user_message_id="user-message-1",
            request=GenerateImageRequest(prompt="maze", output_format="png"),
        )
    ]


# --- The Image Generation skill, inside a chat turn --------------------------------------------


@pytest.mark.asyncio
async def test_the_skill_draws_with_the_accounts_setting_not_the_agents_model(service, drawing):
    _drawing_with("OpenAIAPI", "gpt-5.5")
    agent, conversation = _agent_and_conversation(provider="Anthropic")

    events = await _skill_draws(service, agent, conversation)

    assert drawing.asked["model"] == "gpt-5.5"
    assert drawing.asked["credentials"] == {"api_key": "sk-test"}
    assert [event.event_type for event in events] == [
        SSEEventType.IMAGE_GENERATION_STARTED,
        SSEEventType.LIFECYCLE_NOTIFICATION,
        SSEEventType.IMAGE_GENERATION_COMPLETE,
    ]


@pytest.mark.asyncio
async def test_the_skills_picture_is_saved_as_the_assistants_reply_to_the_turns_message(service):
    _drawing_with("OpenAIAPI", "gpt-5.5")
    agent, conversation = _agent_and_conversation()

    complete = (await _skill_draws(service, agent, conversation))[-1]

    assert complete.image_url.startswith("https://signed.example/")
    assert complete.images[0]["url"] == complete.image_url
    saved = get_message_repository("dynamodb").find_by_conversation(conversation.conversation_id)
    assert [(message.role, len(message.images)) for message in saved] == [("assistant", 1)]


@pytest.mark.asyncio
async def test_the_skill_says_where_to_turn_drawing_on_when_the_account_hasnt(service):
    agent, conversation = _agent_and_conversation(provider="Anthropic")

    with pytest.raises(ImageGenerationNotSupportedError, match="Settings > Image Generation"):
        await _skill_draws(service, agent, conversation)


# --- Asked for directly (dashboard, widget) ------------------------------------------------------


@pytest.mark.asyncio
async def test_a_streamed_drawing_saves_the_prompt_and_the_picture_as_a_turn(service):
    _drawing_with("OpenAIAPI", "gpt-5.5")
    agent, conversation = _agent_and_conversation()

    events = [
        event
        async for event in service.stream_for_dashboard(
            agent=agent, conversation=conversation, actor_email=TEST_USER_EMAIL,
            request=GenerateImageRequest(prompt="maze"),
        )
    ]

    assert [event.event_type for event in events] == [
        SSEEventType.USER_MESSAGE_SAVED,
        SSEEventType.IMAGE_GENERATION_STARTED,
        SSEEventType.LIFECYCLE_NOTIFICATION,
        SSEEventType.ASSISTANT_MESSAGE_SAVED,
        SSEEventType.IMAGE_GENERATION_COMPLETE,
        SSEEventType.STREAM_COMPLETE,
    ]
    complete = events[4]
    # The dashboard reads images through its own authorised route, not a signed S3 link
    assert complete.image_url.endswith(
        f"/conversations/{conversation.conversation_id}/messages/{complete.message_id}/images/{complete.image_id}")
    saved = get_message_repository("dynamodb").find_by_conversation(conversation.conversation_id)
    assert sorted(message.role for message in saved) == ["assistant", "user"]


@pytest.mark.asyncio
async def test_a_widget_drawing_answers_with_signed_urls(service):
    _drawing_with("OpenAIAPI", "gpt-5.5")
    agent, conversation = _agent_and_conversation()

    result = await service.generate_for_widget(
        agent=agent, conversation=conversation, actor_email=TEST_USER_EMAIL,
        request=GenerateImageRequest(prompt="maze"),
    )

    assert result.user_message_id and result.images[0].url.startswith("https://signed.example/")
