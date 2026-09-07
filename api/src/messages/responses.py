"""Response helpers for messages."""

import logging

from src.config import settings
from src.agents.image_generation.storage import ConversationMediaStorage
from src.messages.models import Message, MessageCanvasArtifactResponse, MessageImageResponse, MessageResponse

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

        if message.images:
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

        if message.canvases:
            response.canvases = [
                MessageCanvasArtifactResponse(
                    artifact_id=canvas.artifact_id,
                    title=canvas.title,
                    mime_type=canvas.mime_type,
                    caption=canvas.caption,
                    content_url=f"{settings.api_base_url.rstrip('/')}/artifacts/{canvas.artifact_id}/content",
                    open_url=(
                        f"{settings.frontend_url.rstrip('/')}/dashboard/artifacts/{canvas.artifact_id}"
                        if settings.frontend_url
                        else None
                    ),
                )
                for canvas in message.canvases
            ]

        return response
