"""Response helpers for messages."""

import logging

from src.config import settings
from src.agents.image_generation.storage import ConversationMediaStorage
from src.messages.models import Message, MessageImageResponse, MessageResponse

log = logging.getLogger(__name__)


class MessageResponseFactory:
    """Build message responses with signed generated-image URLs."""

    def __init__(self, storage: ConversationMediaStorage | None = None):
        self._storage = storage

    @property
    def storage(self) -> ConversationMediaStorage:
        if self._storage is None:
            self._storage = ConversationMediaStorage()
        return self._storage

    def to_response(self, message: Message) -> MessageResponse:
        response = message.to_response()
        if not message.images:
            return response

        signed_images: list[MessageImageResponse] = []
        for image in message.images:
            url = (
                f"{settings.api_base_url.rstrip('/')}/conversations/"
                f"{message.conversation_id}/messages/{message.message_id}/images/{image.image_id}"
            )

            signed_images.append(
                MessageImageResponse(
                    image_id=image.image_id,
                    url=url,
                    filename=image.filename,
                    mime_type=image.mime_type,
                    size_bytes=image.size_bytes,
                    width=image.width,
                    height=image.height,
                    prompt=image.prompt,
                    revised_prompt=image.revised_prompt,
                )
            )

        response.images = signed_images
        return response
