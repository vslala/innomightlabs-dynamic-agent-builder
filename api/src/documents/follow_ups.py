"""What an owner does with its documents beyond storing them: the one place owner kinds differ.

A knowledge base indexes a parsed document and takes its page out before the document is deleted; a conversation
does nothing, so for it parsed is ready. Owners register here from their own module (`knowledge/documents.py`), so
`documents` imports none of them.
"""

from typing import Protocol

from src.documents.models import Document, OwnerKind, ParsedDocument


class DocumentFollowUp(Protocol):
    async def after_parse(self, document: Document, reading: ParsedDocument) -> None:
        """Build what the owner keeps from the reading (a KB's chunks and vectors). Raise to fail the document."""
        ...

    def before_delete(self, document: Document) -> None:
        """Remove what the owner built from the document. Raise to stop the delete: nothing else is removed."""
        ...


FOLLOW_UPS: dict[OwnerKind, DocumentFollowUp] = {}


def register(kind: OwnerKind, follow_up: DocumentFollowUp) -> None:
    FOLLOW_UPS[kind] = follow_up
