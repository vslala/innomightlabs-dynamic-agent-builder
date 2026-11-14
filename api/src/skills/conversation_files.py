"""Finding a file the agent names by id, inside the caller's own scope only: a file the member saved (an artifact), an
image uploaded to or generated in this conversation, or a document attached to it. An id from another conversation or
account is never found, so an agent can't name someone else's file.

One finder per place a file lives, tried in order; skills that take file ids (social media, copying into the
workspace) share them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.accounts.owner import member_partition
from src.artifacts.models import Artifact
from src.artifacts.repository import ArtifactRepository
from src.artifacts.service import run_artifact_holder
from src.artifacts.storage import ArtifactStorage
from src.documents.models import DocumentOwner, OwnerKind
from src.documents.service import get_document_service
from src.documents.storage import DocumentStorage
from src.messages.repositories.factory import get_message_repository
from src.skills.runtime_context import account_of
from src.vision.repository import ImageUploadRepository


@dataclass(frozen=True)
class ConversationFile:
    filename: str
    size_bytes: int
    #: "artifact", "upload", "generated_image" or "document"
    kind: str
    read: Callable[[], bytes] = field(compare=False, repr=False)
    #: The S3 key in the conversation media bucket, when it lives there (a preview shows images from it)
    s3_key: str | None = None
    artifact: Artifact | None = None


Finder = Callable[[str, dict[str, Any]], ConversationFile | None]


def find_file(ref: str, context: dict[str, Any]) -> ConversationFile | None:
    return next((found for finder in FINDERS if (found := finder(ref, context))), None)


def _media(key: str) -> Callable[[], bytes]:
    return lambda: ArtifactStorage().get_object_body(key)  # every image lives in the one conversation media bucket


def saved_artifact(ref: str, context: dict[str, Any]) -> ConversationFile | None:
    holder_account, holder_user = run_artifact_holder(context)
    artifact = ArtifactRepository().find_by_id(member_partition(holder_account, holder_user), ref)
    if artifact is None:
        return None
    return ConversationFile(artifact.filename, artifact.size_bytes, "artifact", _media(artifact.s3_key),
                            s3_key=artifact.s3_key, artifact=artifact)


def uploaded_image(ref: str, context: dict[str, Any]) -> ConversationFile | None:
    conversation_id = _conversation(context)
    upload = ImageUploadRepository().find(conversation_id, ref) if conversation_id else None
    if upload is None or upload.account_id != account_of(context):
        return None
    return ConversationFile(upload.filename, upload.size_bytes, "upload", _media(upload.s3_key), s3_key=upload.s3_key)


def generated_image(ref: str, context: dict[str, Any]) -> ConversationFile | None:
    conversation_id = _conversation(context)
    if not conversation_id:
        return None
    for message in get_message_repository().find_by_conversation(conversation_id):
        for image in message.images:
            if image.image_id == ref:
                return ConversationFile(image.filename, image.size_bytes, "generated_image", _media(image.s3_key),
                                        s3_key=image.s3_key)
    return None


def attached_document(ref: str, context: dict[str, Any]) -> ConversationFile | None:
    conversation_id = _conversation(context)
    if not conversation_id:
        return None
    document = get_document_service().get(DocumentOwner(account_of(context), OwnerKind.CONVERSATION, conversation_id), ref)
    if document is None:
        return None
    return ConversationFile(document.filename, document.size_bytes, "document", lambda: DocumentStorage().original(document))


FINDERS: list[Finder] = [saved_artifact, uploaded_image, generated_image, attached_document]


def _conversation(context: dict[str, Any]) -> str:
    return str(context.get("conversation_id") or "").strip()
