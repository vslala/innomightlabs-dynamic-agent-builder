"""Agent image generation orchestration service."""

import json
import logging
from typing import Any, AsyncIterator, cast

from src.agents.image_generation.capabilities import (
    ImageCapability,
    image_capability_registry,
)
from src.agents.image_generation.models import (
    GeneratedImageResponse,
    GeneratedImageBytes,
    GenerateImageRequest,
    GenerateImageResponse,
    ImageGenerationOptions,
)
from src.agents.image_generation.provider import ImageProviderFactory
from src.agents.image_generation.storage import ConversationMediaStorage
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.auth.openai_oauth import ensure_valid_openai_credentials
from src.config import settings
from src.conversations.models import Conversation
from src.conversations.repository import ConversationRepository
from src.crypto import decrypt
from src.messages.models import Message, MessageImage
from src.messages.repositories import MessageRepository, get_message_repository
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository
from src.llm.events import SSEEvent, SSEEventType

log = logging.getLogger(__name__)


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
        provider_factory: ImageProviderFactory | None = None,
    ):
        self.agent_repo = agent_repo or AgentRepository()
        self.conversation_repo = conversation_repo or ConversationRepository()
        self.message_repo = message_repo or get_message_repository("dynamodb")
        self.provider_settings_repo = provider_settings_repo or get_provider_settings_repository()
        self.storage = storage or ConversationMediaStorage()
        self.provider_factory = provider_factory or ImageProviderFactory()

    async def generate_for_dashboard(
        self,
        *,
        agent_id: str,
        conversation_id: str,
        user_email: str,
        request: GenerateImageRequest,
    ) -> GenerateImageResponse:
        agent, conversation = self._load_dashboard_context(agent_id, conversation_id, user_email)
        result = await self._generate(
            agent=agent,
            conversation=conversation,
            owner_email=user_email,
            actor_email=user_email,
            request=request,
        )
        for image in result.images:
            image.url = (
                f"{settings.api_base_url.rstrip('/')}/conversations/"
                f"{conversation.conversation_id}/messages/{result.assistant_message_id}/images/{image.image_id}"
            )
        return result

    async def stream_for_dashboard(
        self,
        *,
        agent_id: str,
        conversation_id: str,
        user_email: str,
        request: GenerateImageRequest,
    ) -> AsyncIterator[SSEEvent]:
        agent, conversation = self._load_dashboard_context(agent_id, conversation_id, user_email)
        async for event in self._stream_generate(
            agent=agent,
            conversation=conversation,
            owner_email=user_email,
            actor_email=user_email,
            request=request,
            dashboard_urls=True,
        ):
            yield event

    async def generate_for_widget(
        self,
        *,
        agent: Agent,
        conversation: Conversation,
        owner_email: str,
        actor_email: str,
        request: GenerateImageRequest,
    ) -> GenerateImageResponse:
        return await self._generate(
            agent=agent,
            conversation=conversation,
            owner_email=owner_email,
            actor_email=actor_email,
            request=request,
        )

    async def stream_for_widget(
        self,
        *,
        agent: Agent,
        conversation: Conversation,
        owner_email: str,
        actor_email: str,
        request: GenerateImageRequest,
    ) -> AsyncIterator[SSEEvent]:
        async for event in self._stream_generate(
            agent=agent,
            conversation=conversation,
            owner_email=owner_email,
            actor_email=actor_email,
            request=request,
            dashboard_urls=False,
        ):
            yield event

    async def _generate(
        self,
        *,
        agent: Agent,
        conversation: Conversation,
        owner_email: str,
        actor_email: str,
        request: GenerateImageRequest,
    ) -> GenerateImageResponse:
        provider_settings = self._validate_and_load_provider_settings(agent, owner_email)

        user_msg = Message(
            conversation_id=conversation.conversation_id,
            created_by=actor_email,
            role="user",
            content=request.prompt,
        )
        self.message_repo.save(user_msg)

        credentials = await self._load_credentials(agent.agent_provider, provider_settings)
        provider = self.provider_factory.get(agent.agent_provider)
        generated_images = await provider.generate(
            prompt=request.prompt,
            credentials=credentials,
            model=agent.agent_model or "",
            options=ImageGenerationOptions(
                size=request.size,
                quality=request.quality,
                output_format=request.output_format,
            ),
        )

        return self._persist_generated_images(
            agent=agent,
            conversation=conversation,
            actor_email=actor_email,
            prompt=request.prompt,
            user_message_id=user_msg.message_id,
            generated_images=generated_images,
            dashboard_urls=False,
        )

    async def _stream_generate(
        self,
        *,
        agent: Agent,
        conversation: Conversation,
        owner_email: str,
        actor_email: str,
        request: GenerateImageRequest,
        dashboard_urls: bool,
    ) -> AsyncIterator[SSEEvent]:
        provider_settings = self._validate_and_load_provider_settings(agent, owner_email)

        user_msg = Message(
            conversation_id=conversation.conversation_id,
            created_by=actor_email,
            role="user",
            content=request.prompt,
        )
        self.message_repo.save(user_msg)
        yield SSEEvent(
            event_type=SSEEventType.USER_MESSAGE_SAVED,
            content="User message saved",
            message_id=user_msg.message_id,
        )
        yield SSEEvent(
            event_type=SSEEventType.IMAGE_GENERATION_STARTED,
            content="Starting image generation...",
        )

        credentials = await self._load_credentials(agent.agent_provider, provider_settings)
        provider = self.provider_factory.get(agent.agent_provider)
        generated_images: list[GeneratedImageBytes] = []

        async for provider_event in provider.stream_generate(
            prompt=request.prompt,
            credentials=credentials,
            model=agent.agent_model or "",
            options=ImageGenerationOptions(
                size=request.size,
                quality=request.quality,
                output_format=request.output_format,
            ),
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
                yield SSEEvent(
                    event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                    content="Generating image...",
                )
            elif provider_event.kind == "image" and provider_event.image:
                generated_images.append(provider_event.image)

        if not generated_images:
            raise AgentImageGenerationError("Image generation completed without image output")

        result = self._persist_generated_images(
            agent=agent,
            conversation=conversation,
            actor_email=actor_email,
            prompt=request.prompt,
            user_message_id=user_msg.message_id,
            generated_images=generated_images,
            dashboard_urls=dashboard_urls,
        )
        first_image = result.images[0] if result.images else None
        yield SSEEvent(
            event_type=SSEEventType.ASSISTANT_MESSAGE_SAVED,
            content="Assistant message saved",
            message_id=result.assistant_message_id,
        )
        yield SSEEvent(
            event_type=SSEEventType.IMAGE_GENERATION_COMPLETE,
            content="Image generation complete",
            message_id=result.assistant_message_id,
            image_url=first_image.url if first_image else None,
            image_id=first_image.image_id if first_image else None,
            image_filename=first_image.filename if first_image else None,
            image_mime_type=first_image.mime_type if first_image else None,
            image_width=first_image.width if first_image else None,
            image_height=first_image.height if first_image else None,
            images=[image.model_dump(mode="json") for image in result.images],
        )
        yield SSEEvent(
            event_type=SSEEventType.STREAM_COMPLETE,
            content="Response complete",
        )

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

    def _load_dashboard_context(
        self,
        agent_id: str,
        conversation_id: str,
        user_email: str,
    ) -> tuple[Agent, Conversation]:
        agent = self.agent_repo.find_agent_by_id(agent_id, user_email)
        if not agent:
            raise ImageGenerationNotFoundError("Agent not found")

        conversation = self.conversation_repo.find_by_id(conversation_id, user_email)
        if not conversation:
            raise ImageGenerationNotFoundError("Conversation not found")

        if conversation.agent_id != agent_id:
            raise ImageGenerationConflictError("Conversation does not belong to this agent")

        return agent, conversation

    def _validate_and_load_provider_settings(self, agent: Agent, owner_email: str):
        if not image_capability_registry.supports(
            agent.agent_provider,
            agent.agent_model,
            ImageCapability.GENERATION,
        ):
            raise ImageGenerationNotSupportedError(
                "This agent's selected model does not support image generation."
            )

        provider_settings = self.provider_settings_repo.find_by_provider(
            owner_email,
            agent.agent_provider,
        )
        if not provider_settings:
            raise AgentImageGenerationError(
                f"Provider '{agent.agent_provider}' is not configured."
            )
        return provider_settings

    async def _load_credentials(self, provider_name: str, provider_settings) -> dict[Any, Any]:
        if provider_name == "OpenAI":
            openai_credentials = await ensure_valid_openai_credentials(
                provider_settings,
                self.provider_settings_repo,
            )
            return cast(dict[Any, Any], openai_credentials.model_dump(mode="json"))

        credentials = json.loads(decrypt(provider_settings.encrypted_credentials))
        return cast(dict[Any, Any], credentials) if isinstance(credentials, dict) else {}
