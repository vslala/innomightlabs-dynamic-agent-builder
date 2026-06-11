from types import SimpleNamespace

import pytest

from src.agents.image_generation.models import GeneratedImageBytes, GenerateImageRequest
from src.agents.image_generation.service import AgentImageGenerationService
from src.agents.models import Agent
from src.conversations.models import Conversation
from src.llm.events import SSEEventType


class FakeMessageRepository:
    def __init__(self):
        self.saved = []

    def save(self, message):
        self.saved.append(message)
        return message


class FakeStorage:
    def build_image_key(self, *, agent_id, conversation_id, message_id, extension):
        return f"agents/{agent_id}/conversations/{conversation_id}/messages/{message_id}/image.{extension}"

    def put_image(self, *, key, body, content_type):
        return None

    def presign_get_url(self, key):
        return f"https://signed.example/{key}?signature=test"


class FakeProvider:
    async def stream_generate(self, **kwargs):
        yield SimpleNamespace(kind="generating")
        yield SimpleNamespace(
            kind="image",
            image=GeneratedImageBytes(
                data=b"fake-image",
                output_format="png",
                mime_type="image/png",
                prompt=kwargs["prompt"],
                width=256,
                height=256,
            ),
        )


class FakeProviderFactory:
    def get(self, provider_name):
        return FakeProvider()


class FakeAgentImageGenerationService(AgentImageGenerationService):
    def _load_agent_turn_context(self, *, agent_id, conversation_id, owner_email, actor_email):
        return (
            Agent(
                agent_id=agent_id,
                agent_name="Image Agent",
                agent_architecture="krishna-memgpt",
                agent_provider="OpenAI",
                agent_model="gpt-5.4",
                agent_persona="Generate images.",
                created_by=owner_email,
            ),
            Conversation(
                conversation_id=conversation_id,
                title="Image conversation",
                agent_id=agent_id,
                created_by=actor_email,
            ),
        )

    def _validate_and_load_provider_settings(self, agent, owner_email):
        return SimpleNamespace()

    async def _load_credentials(self, provider_name, provider_settings):
        return {"access_token": "token"}


@pytest.mark.asyncio
async def test_stream_for_agent_turn_completion_includes_signed_image_url():
    service = FakeAgentImageGenerationService(
        message_repo=FakeMessageRepository(),
        storage=FakeStorage(),
        provider_factory=FakeProviderFactory(),
    )

    events = [
        event
        async for event in service.stream_for_agent_turn(
            agent_id="agent-1",
            conversation_id="conversation-1",
            owner_email="owner@example.com",
            actor_email="actor@example.com",
            user_message_id="user-message-1",
            request=GenerateImageRequest(prompt="maze", output_format="png"),
        )
    ]

    complete = next(
        event
        for event in events
        if event.event_type == SSEEventType.IMAGE_GENERATION_COMPLETE
    )

    assert complete.image_url
    assert complete.image_url.startswith("https://signed.example/")
    assert complete.images
    assert complete.images[0]["url"].startswith("https://signed.example/")
    assert complete.images[0]["url"] == complete.image_url
