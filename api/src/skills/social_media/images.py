"""Turning the image ids the agent was given into bytes to post. An id is always looked up inside the caller's own
scope, so an agent can't name another conversation's or account's image."""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from typing import Any

from src.artifacts.models import Artifact
from src.artifacts.storage import ArtifactStorage
from src.connectors.social.media import SourceImage
from src.skills.conversation_files import find_file

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
    found = find_file(ref, context)
    if found is None or found.kind == "document" or found.s3_key is None:
        raise ValueError(f"No image {ref} in this conversation")
    if found.artifact is not None and not _is_picture(found.artifact):
        raise ValueError(f"{ref} is not an image. Save a picture with upload_file as artifact_type image.")
    return found.s3_key


def _is_picture(artifact: Artifact) -> bool:
    """An image artifact, or a picture saved as a plain file before images had their own type. Whether it can really
    be read is checked when it is prepared for the network."""
    if artifact.artifact_type == "image":
        return True
    guessed = mimetypes.guess_type(artifact.filename)[0] or ""
    return artifact.artifact_type == "file" and guessed.startswith("image/") and guessed != "image/svg+xml"


def _strings(value: Any, name: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return [str(item).strip() for item in value if str(item).strip()]
