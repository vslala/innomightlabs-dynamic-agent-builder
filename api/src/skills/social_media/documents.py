"""Turning the document id the agent was given into a file to post. Like images, an id is looked up only inside the
caller's own scope: a file the member saved, or a document attached to this conversation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.accounts.owner import member_partition
from src.artifacts.repository import ArtifactRepository
from src.artifacts.service import run_artifact_holder
from src.artifacts.storage import ArtifactStorage
from src.connectors.social.documents import SourceDocument
from src.documents.models import DocumentOwner, OwnerKind
from src.documents.service import get_document_service
from src.documents.storage import DocumentStorage
from src.skills.runtime_context import account_of

MAX_TITLE = 400


@dataclass(frozen=True)
class DocumentLocation:
    """Enough to plan a post (name, size) and, only when it is published, to read the file."""

    filename: str
    size_bytes: int
    title: str
    read: Callable[[], bytes] = field(compare=False, repr=False)

    def load(self) -> SourceDocument:
        return SourceDocument(data=self.read(), filename=self.filename, title=self.title)


def resolve_document(arguments: dict[str, Any], context: dict[str, Any]) -> DocumentLocation | None:
    ref = str(arguments.get("document") or "").strip()
    if not ref:
        return None
    title = " ".join(str(arguments.get("document_title") or "").split())[:MAX_TITLE]
    found = _saved_file(ref, title, context) or _attached_document(ref, title, context)
    if found is None:
        raise ValueError(f"No document {ref} in this conversation. Use the id of a file saved with upload_file or of an "
                         "<attached_document>.")
    return found


def _saved_file(ref: str, title: str, context: dict[str, Any]) -> DocumentLocation | None:
    holder_account, holder_user = run_artifact_holder(context)
    artifact = ArtifactRepository().find_by_id(member_partition(holder_account, holder_user), ref)
    if artifact is None:
        return None
    key = artifact.s3_key
    return DocumentLocation(artifact.filename, artifact.size_bytes, title, lambda: ArtifactStorage().get_object_body(key))


def _attached_document(ref: str, title: str, context: dict[str, Any]) -> DocumentLocation | None:
    conversation_id = str(context.get("conversation_id") or "").strip()
    if not conversation_id:
        return None
    owner = DocumentOwner(account_of(context), OwnerKind.CONVERSATION, conversation_id)
    document = get_document_service().get(owner, ref)
    if document is None:
        return None
    return DocumentLocation(document.filename, document.size_bytes, title, lambda: DocumentStorage().original(document))
