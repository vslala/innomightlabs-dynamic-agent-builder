"""Reading, storing and serving files for an owner (a knowledge base, a conversation). See CONTRIBUTION.md."""

from src.documents.models import (
    Document,
    DocumentOwner,
    DocumentReadError,
    DocumentResponse,
    DocumentStatus,
    OwnerKind,
    ParsedDocument,
    ParsedPage,
    ParsedTable,
    UnsupportedDocument,
)
from src.documents.reader import read_document

__all__ = [
    "Document",
    "DocumentOwner",
    "DocumentReadError",
    "DocumentResponse",
    "DocumentStatus",
    "OwnerKind",
    "ParsedDocument",
    "ParsedPage",
    "ParsedTable",
    "UnsupportedDocument",
    "read_document",
]
