"""Taking an image from a person to a message: store it pending, then bind it to the message that sends it."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from uuid import uuid4

from src.agents.image_generation.storage import ConversationMediaStorage, StoredImage
from src.agents.models import Agent
from src.messages.models import ImageAttachment
from src.vision.errors import ImageInputError
from src.vision.images import normalise_image
from src.vision.models import ImageInputLimits, ImageUpload
from src.vision.policy import require_image_input
from src.vision.repository import ImageUploadRepository

log = logging.getLogger(__name__)

#: Names a clipboard paste or a camera gives every image, which say nothing about this one.
GENERIC_STEMS = {"", "image", "img", "blob", "unnamed"}
#: A name safe to show and to put in a header: no path, no spaces or quotes.
UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
PENDING_TAG = "retention=pending-upload"
ATTACHED_TAGS = {"retention": "conversation"}


class ImageUploadService:
    def __init__(
        self,
        repository: ImageUploadRepository | None = None,
        storage: ConversationMediaStorage | None = None,
    ) -> None:
        self.repository = repository or ImageUploadRepository()
        self._storage = storage

    @property
    def storage(self) -> ConversationMediaStorage:
        if self._storage is None:
            self._storage = ConversationMediaStorage()
        return self._storage

    def store(self, *, agent: Agent, conversation_id: str, uploaded_by: str, filename: str, raw: bytes) -> ImageUpload:
        """Validate, normalise and save one pending image."""
        availability = require_image_input(agent)
        image = normalise_image(raw, availability.limits)
        image_id = str(uuid4())
        upload = ImageUpload(
            image_id=image_id,
            conversation_id=conversation_id,
            agent_id=agent.agent_id,
            account_id=agent.account_id,
            uploaded_by=uploaded_by,
            s3_key=self.storage.build_upload_key(
                agent_id=agent.agent_id, conversation_id=conversation_id, image_id=image_id, extension=image.extension
            ),
            filename=_display_name(filename, image.extension),
            mime_type=image.mime_type,
            size_bytes=len(image.body),
            width=image.width,
            height=image.height,
        )
        # The bytes first: a ledger row without bytes would pass attach() and fail every read.
        self.storage.put_image(key=upload.s3_key, body=image.body, content_type=image.mime_type, tagging=PENDING_TAG)
        return self.repository.save(upload)

    def attach(
        self, *, agent: Agent, conversation_id: str, actor_id: str, image_ids: list[str]
    ) -> list[ImageAttachment]:
        """Bind pending uploads to the message being sent.

        Each must be this conversation's, this actor's and unexpired; anything else is `image_not_found`.
        """
        if not image_ids:
            return []
        availability = require_image_input(agent)
        unique_ids = list(dict.fromkeys(image_ids))
        _require_within_limit(unique_ids, availability.limits)

        attachments: list[ImageAttachment] = []
        for image_id in unique_ids:
            upload = self.repository.claim(conversation_id, image_id, uploaded_by=actor_id)
            if upload is None:
                raise ImageInputError("image_not_found", "An attached image expired or wasn't found. Please attach it again.")
            self._retag_attached(upload)
            attachments.append(_attachment_of(upload))
        return attachments

    def open_bytes(self, *, conversation_id: str, image_id: str) -> StoredImage:
        """The stored bytes, found through the conversation's ledger row."""
        upload = self.repository.find(conversation_id, image_id)
        if upload is None:
            raise ImageInputError("image_not_found", "Image not found.", status_code=404)
        return self.storage.get_image(upload.s3_key)

    def _retag_attached(self, upload: ImageUpload) -> None:
        try:
            self.storage.retag(upload.s3_key, ATTACHED_TAGS)
        except Exception:
            # The lifecycle rule would then expire a sent image after a day, so this is worth a loud log.
            log.error("Could not retag attached image %s", upload.s3_key, exc_info=True)


def _attachment_of(upload: ImageUpload) -> ImageAttachment:
    return ImageAttachment(
        image_id=upload.image_id,
        s3_key=upload.s3_key,
        filename=upload.filename,
        mime_type=upload.mime_type,
        size_bytes=upload.size_bytes,
        width=upload.width,
        height=upload.height,
    )


def _require_within_limit(image_ids: list[str], limits: ImageInputLimits) -> None:
    if len(image_ids) > limits.max_images_per_message:
        raise ImageInputError("too_many_images", f"Up to {limits.max_images_per_message} images per message.")


def _display_name(filename: str, extension: str) -> str:
    name = filename.strip().rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = UNSAFE_FILENAME_CHARS.sub("-", os.path.splitext(name)[0]).strip(".-")[:80]
    if stem.lower() in GENERIC_STEMS:
        stem = "pasted-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stem}.{extension}"
