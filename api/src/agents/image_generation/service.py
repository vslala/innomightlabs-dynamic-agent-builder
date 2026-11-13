"""Agent image generation orchestration service."""

import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, cast

from src.agents.image_generation.models import (
    GeneratedImageResponse,
    GenerateImageRequest,
    GenerateImageResponse,
)
from src.agents.image_generation.settings import ImageGenerationSettingsRepository
from src.agents.image_generation.storage import ConversationMediaStorage
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.config import settings
from src.conversations.models import Conversation
from src.conversations.repository import ConversationRepository
from src.llm.credentials import load_provider_credentials
from src.llm.images import GeneratedImageBytes, ImageGenerator, collect_images
from src.llm.providers import find_provider
from src.messages.models import Message, MessageImage
from src.messages.repositories import MessageRepository, get_message_repository
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository
from src.llm.events import SSEEvent, SSEEventType

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentConversationContext:
    agent: Agent
    conversation: Conversation


@dataclass(frozen=True)
class Artist:
    """The provider and model that draw, and the account's settings for that provider."""

    provider_name: str
    model: str
    provider_settings: ProviderSettings
    images: ImageGenerator


class AgentImageGenerationError(Exception):
    """Base exception for agent image generation failures."""


class ImageGenerationNotSupportedError(AgentImageGenerationError):
    """Raised when the selected agent model does not support image generation."""


class ImageGenerationNotFoundError(AgentImageGenerationError):
    """Raised when an agent or conversation cannot be found."""


class ImageGenerationConflictError(AgentImageGenerationError):
    """Raised when a conversation does not belong to the requested agent."""


class AgentImageGenerationService:
    """Generate images through an agent and persist the resulting chat turn."""

    def __init__(
        self,
        *,
        agent_repo: AgentRepository | None = None,
        conversation_repo: ConversationRepository | None = None,
        message_repo: MessageRepository | None = None,
        provider_settings_repo: ProviderSettingsRepository | None = None,
        storage: ConversationMediaStorage | None = None,
        image_settings_repo: ImageGenerationSettingsRepository | None = None,
    ):
        self.agent_repo = agent_repo or AgentRepository()
        self.conversation_repo = conversation_repo or ConversationRepository()
        self.message_repo = message_repo or get_message_repository("dynamodb")
        self.provider_settings_repo = provider_settings_repo or get_provider_settings_repository()
        self.storage = storage or ConversationMediaStorage()
        self.image_settings_repo = image_settings_repo or ImageGenerationSettingsRepository()

    async def generate_for_dashboard(
        self,
        *,
        agent: Agent,
        conversation: Conversation,
        actor_email: str,
        request: GenerateImageRequest,
    ) -> GenerateImageResponse:
        """The route has authorized the caller for this agent and conversation. Image URLs point at the dashboard's
        own image route."""
        return await self._generate_chat_turn(agent, conversation, actor_email, request, dashboard_urls=True)

    async def generate_for_widget(
        self,
        *,
        agent: Agent,
        conversation: Conversation,
        actor_email: str,
        request: GenerateImageRequest,
    ) -> GenerateImageResponse:
        return await self._generate_chat_turn(agent, conversation, actor_email, request, dashboard_urls=False)

    async def stream_for_dashboard(
        self,
        *,
        agent: Agent,
        conversation: Conversation,
        actor_email: str,
        request: GenerateImageRequest,
    ) -> AsyncIterator[SSEEvent]:
        async for event in self._stream_chat_turn(agent, conversation, actor_email, request, dashboard_urls=True):
            yield event

    async def stream_for_widget(
        self,
        *,
        agent: Agent,
        conversation: Conversation,
        actor_email: str,
        request: GenerateImageRequest,
    ) -> AsyncIterator[SSEEvent]:
        async for event in self._stream_chat_turn(agent, conversation, actor_email, request, dashboard_urls=False):
            yield event

    async def stream_for_agent_turn(
        self,
        *,
        agent_id: str,
        conversation_id: str,
        actor_email: str,
        request: GenerateImageRequest,
        user_message_id: str | None = None,
    ) -> AsyncIterator[SSEEvent]:
        """The Image Generation skill, inside a running chat turn: the turn already saved the person's message and
        goes on after the picture, so only the drawing's own events are sent."""
        context = self._load_agent_turn_context(agent_id=agent_id, conversation_id=conversation_id)
        artist = self._artist_for(context.agent)

        yield SSEEvent(event_type=SSEEventType.IMAGE_GENERATION_STARTED, content="Starting image generation...")
        drawn: list[GeneratedImageBytes] = []
        async for event in self._draw_streaming(artist, request, drawn):
            yield event

        result = self._persist_generated_images(
            agent=context.agent,
            conversation=context.conversation,
            actor_email=actor_email,
            prompt=request.prompt,
            user_message_id=user_message_id or "",
            generated_images=drawn,
            dashboard_urls=False,
        )
        yield _completion_event(result)

    async def _generate_chat_turn(
        self,
        agent: Agent,
        conversation: Conversation,
        actor_email: str,
        request: GenerateImageRequest,
        *,
        dashboard_urls: bool,
    ) -> GenerateImageResponse:
        """A drawing asked for directly: saves the person's prompt and the assistant's images as a chat turn."""
        artist = self._artist_for(agent)
        user_message = self._save_prompt(conversation, actor_email, request)
        drawn = await self._draw(artist, request)
        return self._persist_generated_images(
            agent=agent,
            conversation=conversation,
            actor_email=actor_email,
            prompt=request.prompt,
            user_message_id=user_message.message_id,
            generated_images=drawn,
            dashboard_urls=dashboard_urls,
        )

    async def _stream_chat_turn(
        self,
        agent: Agent,
        conversation: Conversation,
        actor_email: str,
        request: GenerateImageRequest,
        *,
        dashboard_urls: bool,
    ) -> AsyncIterator[SSEEvent]:
        """`_generate_chat_turn` as a stream: the whole turn's events, from the saved prompt to the stream's end."""
        artist = self._artist_for(agent)
        user_message = self._save_prompt(conversation, actor_email, request)
        yield SSEEvent(
            event_type=SSEEventType.USER_MESSAGE_SAVED,
            content="User message saved",
            message_id=user_message.message_id,
        )
        yield SSEEvent(event_type=SSEEventType.IMAGE_GENERATION_STARTED, content="Starting image generation...")

        drawn: list[GeneratedImageBytes] = []
        async for event in self._draw_streaming(artist, request, drawn):
            yield event

        result = self._persist_generated_images(
            agent=agent,
            conversation=conversation,
            actor_email=actor_email,
            prompt=request.prompt,
            user_message_id=user_message.message_id,
            generated_images=drawn,
            dashboard_urls=dashboard_urls,
        )
        yield SSEEvent(
            event_type=SSEEventType.ASSISTANT_MESSAGE_SAVED,
            content="Assistant message saved",
            message_id=result.assistant_message_id,
        )
        yield _completion_event(result)
        yield SSEEvent(event_type=SSEEventType.STREAM_COMPLETE, content="Response complete")

    def _save_prompt(self, conversation: Conversation, actor_email: str, request: GenerateImageRequest) -> Message:
        return self.message_repo.save(
            Message(
                conversation_id=conversation.conversation_id,
                created_by=actor_email,
                role="user",
                content=request.prompt,
            )
        )

    async def _draw(self, artist: "Artist", request: GenerateImageRequest) -> list[GeneratedImageBytes]:
        credentials = await self._load_credentials(artist.provider_name, artist.provider_settings)
        return await collect_images(
            artist.images.draw(
                prompt=request.prompt, credentials=credentials, model=artist.model, options=request.options()
            )
        )

    async def _draw_streaming(
        self, artist: "Artist", request: GenerateImageRequest, drawn: list[GeneratedImageBytes]
    ) -> AsyncIterator[SSEEvent]:
        """The drawing's progress as SSE events; the finished pictures are appended to `drawn`, since an async
        generator can't also return them."""
        credentials = await self._load_credentials(artist.provider_name, artist.provider_settings)
        async for provider_event in artist.images.draw(
            prompt=request.prompt,
            credentials=credentials,
            model=artist.model,
            options=request.options(),
        ):
            if provider_event.kind == "partial" and provider_event.image_b64:
                yield SSEEvent(
                    event_type=SSEEventType.IMAGE_GENERATION_PARTIAL,
                    content="Rendering image preview...",
                    image_b64=provider_event.image_b64,
                    image_mime_type=provider_event.mime_type,
                    image_width=provider_event.width,
                    image_height=provider_event.height,
                )
            elif provider_event.kind == "generating":
                yield SSEEvent(event_type=SSEEventType.LIFECYCLE_NOTIFICATION, content="Generating image...")
            elif provider_event.kind == "image" and provider_event.image:
                drawn.append(provider_event.image)

        if not drawn:
            raise AgentImageGenerationError("Image generation completed without image output")

    def _persist_generated_images(
        self,
        *,
        agent: Agent,
        conversation: Conversation,
        actor_email: str,
        prompt: str,
        user_message_id: str,
        generated_images: list[GeneratedImageBytes],
        dashboard_urls: bool,
    ) -> GenerateImageResponse:
        assistant_msg = Message(
            conversation_id=conversation.conversation_id,
            created_by=actor_email,
            role="assistant",
            content=f"Generated image: {prompt}",
        )

        response_images: list[GeneratedImageResponse] = []
        for index, generated in enumerate(generated_images, start=1):
            extension = generated.output_format.lower().lstrip(".") or "png"
            key = self.storage.build_image_key(
                agent_id=agent.agent_id,
                conversation_id=conversation.conversation_id,
                message_id=assistant_msg.message_id,
                extension=extension,
            )
            self.storage.put_image(
                key=key,
                body=generated.data,
                content_type=generated.mime_type,
            )

            filename = f"generated-image-{index}.{extension}"
            image = MessageImage(
                s3_key=key,
                filename=filename,
                mime_type=generated.mime_type,
                size_bytes=len(generated.data),
                width=generated.width,
                height=generated.height,
                prompt=generated.prompt,
                revised_prompt=generated.revised_prompt,
                quality=generated.quality,
                background=generated.background,
            )
            assistant_msg.images.append(image)
            response_images.append(
                GeneratedImageResponse(
                    image_id=image.image_id,
                    url=(
                        f"{settings.api_base_url.rstrip('/')}/conversations/"
                        f"{conversation.conversation_id}/messages/{assistant_msg.message_id}/images/{image.image_id}"
                        if dashboard_urls
                        else self.storage.presign_get_url(key)
                    ),
                    s3_key=key,
                    filename=filename,
                    mime_type=generated.mime_type,
                    width=generated.width,
                    height=generated.height,
                    size_bytes=len(generated.data),
                    prompt=generated.prompt,
                    revised_prompt=generated.revised_prompt,
                )
            )

        self.message_repo.save(assistant_msg)

        return GenerateImageResponse(
            agent_id=agent.agent_id,
            conversation_id=conversation.conversation_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_msg.message_id,
            images=response_images,
        )

    def _load_agent_turn_context(
        self,
        *,
        agent_id: str,
        conversation_id: str,
    ) -> AgentConversationContext:
        # The agent of the running turn, found by its id
        agent = self.agent_repo.get(agent_id)
        if not agent:
            raise ImageGenerationNotFoundError("Agent not found")

        # The conversation of the running turn, whoever started it (the owner, or a member on a shared agent)
        conversation = self.conversation_repo.get(conversation_id)
        if not conversation:
            raise ImageGenerationNotFoundError("Conversation not found")

        if conversation.agent_id != agent_id:
            raise ImageGenerationConflictError("Conversation does not belong to this agent")

        return AgentConversationContext(agent=agent, conversation=conversation)

    def _artist_for(self, agent: Agent) -> "Artist":
        """Who draws for this agent: the account's Image Generation setting, whatever model the agent thinks with. Its
        model was checked against the provider's catalog when the admin saved it."""
        chosen = self.image_settings_repo.find_in_account(agent.account_id)
        if not chosen or not chosen.is_configured:
            raise ImageGenerationNotSupportedError(
                "Image generation is off. An admin can turn it on in Settings > Image Generation."
            )
        provider_name, model = str(chosen.provider_name), str(chosen.model_name)
        found = find_provider(provider_name)
        if not found or not found.images:
            raise ImageGenerationNotSupportedError(
                f"{provider_name} can't draw images. An admin can choose a provider that can in Settings > "
                "Image Generation."
            )
        # The agent's account's provider, whoever asks
        provider_settings = self.provider_settings_repo.find_by_provider(agent.account_id, provider_name)
        if not provider_settings:
            raise AgentImageGenerationError(f"Provider '{provider_name}' is not configured.")
        return Artist(provider_name=provider_name, model=model, provider_settings=provider_settings, images=found.images)

    async def _load_credentials(self, provider_name: str, provider_settings) -> dict[Any, Any]:
        return cast(
            dict[Any, Any],
            await load_provider_credentials(
                provider_name=provider_name,
                provider_settings=provider_settings,
                provider_settings_repo=self.provider_settings_repo,
            ),
        )


def _completion_event(result: GenerateImageResponse) -> SSEEvent:
    """The finished drawing: every image, with the first one's details at the top level for older clients."""
    first = result.images[0] if result.images else None
    return SSEEvent(
        event_type=SSEEventType.IMAGE_GENERATION_COMPLETE,
        content="Image generation complete",
        message_id=result.assistant_message_id,
        image_url=first.url if first else None,
        image_id=first.image_id if first else None,
        image_filename=first.filename if first else None,
        image_mime_type=first.mime_type if first else None,
        image_width=first.width if first else None,
        image_height=first.height if first else None,
        images=[image.model_dump(mode="json") for image in result.images],
    )
