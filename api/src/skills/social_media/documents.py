"""Turning the document id the agent was given into a file to post. Like images, an id is looked up only inside the
caller's own scope (`skills/conversation_files.py`): a file the member saved, or a document attached to this
conversation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.connectors.social.documents import SourceDocument
from src.skills.conversation_files import find_file

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
    found = find_file(ref, context)
    if found is None or found.kind not in {"artifact", "document"}:
        raise ValueError(f"No document {ref} in this conversation. Use the id of a file saved with upload_file or of an "
                         "<attached_document>.")
    return DocumentLocation(found.filename, found.size_bytes, title, found.read)
