"""Turning the image ids the agent was given into bytes to post. An id is always looked up inside the caller's own
scope, so an agent can't name another conversation's or account's image."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.accounts.owner import member_partition
from src.artifacts.repository import ArtifactRepository
from src.artifacts.service import run_artifact_holder
from src.artifacts.storage import ArtifactStorage
from src.connectors.social.media import SourceImage
from src.messages.repositories.factory import get_message_repository
from src.skills.runtime_context import account_of
from src.vision.repository import ImageUploadRepository

MAX_ALT_TEXT = 4000


@dataclass(frozen=True)
class ImageLocation:
    s3_key: str
    alt_text: str = ""


def resolve_images(arguments: dict[str, Any], context: dict[str, Any]) -> list[ImageLocation]:
    """Where each of `images` lives. Ids: an artifact the member owns, an upload in this conversation, or an image the
    agent generated in this conversation."""
    refs = _strings(arguments.get("images"), "images")
    alt_texts = _strings(arguments.get("alt_texts"), "alt_texts")
    if len(alt_texts) > len(refs):
        raise ValueError("alt_texts has more entries than images")
    return [
        ImageLocation(_find(ref, context), alt_texts[index][:MAX_ALT_TEXT] if index < len(alt_texts) else "")
        for index, ref in enumerate(refs)
    ]


def load_images(locations: list[ImageLocation]) -> tuple[SourceImage, ...]:
    storage = ArtifactStorage()  # every image lives in the one conversation media bucket
    return tuple(SourceImage(storage.get_object_body(location.s3_key), location.alt_text) for location in locations)


def _find(ref: str, context: dict[str, Any]) -> str:
    account_id = account_of(context)
    holder_account, holder_user = run_artifact_holder(context)
    artifact = ArtifactRepository().find_by_id(member_partition(holder_account, holder_user), ref)
    if artifact:
        if artifact.artifact_type != "image":
            raise ValueError(f"{ref} is not an image")
        return artifact.s3_key

    conversation_id = str(context.get("conversation_id") or "").strip()
    if conversation_id:
        upload = ImageUploadRepository().find(conversation_id, ref)
        if upload and upload.account_id == account_id:
            return upload.s3_key
        for message in get_message_repository().find_by_conversation(conversation_id):
            for image in message.images:
                if image.image_id == ref:
                    return image.s3_key
    raise ValueError(f"No image {ref} in this conversation")


def _strings(value: Any, name: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return [str(item).strip() for item in value if str(item).strip()]
