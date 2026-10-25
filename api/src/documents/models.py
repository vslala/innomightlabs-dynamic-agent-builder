"""Documents: what reading a file gives back, whichever parser read it, and the stored record of a document.

Keys (docs/LLD-documents.md, section 3.3):
    Document: pk=DocumentOwner#{owner_kind}#{owner_id}, sk=Document#{document_id}
The owner is the resource that holds the document (a knowledge base, a conversation), never a person: who uploaded it
is `created_by`, kept for audit and never part of a key or an access rule.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

IMAGE_LINK = re.compile(r"!\[[^\]]*\]\([^)]*\)")
SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


class DocumentReadError(Exception):
    """The file couldn't be read; the message says why, for the upload's log and the user."""


class UnsupportedDocument(DocumentReadError):
    """No parser reads this kind of file."""


class DocumentNotFound(DocumentReadError):
    """No such document for this owner (or it is being deleted)."""


@dataclass(frozen=True)
class ParsedTable:
    page: int
    rows: list[list[str]]


@dataclass(frozen=True)
class ParsedPage:
    number: int
    markdown: str = ""
    #: The page as rendered (PNG), when the parser renders pages (Docling, for PDFs).
    image: Optional[bytes] = None


@dataclass(frozen=True)
class OutlineEntry:
    """A heading: where a section starts in the Markdown (`offset`), and the page it is on when the parser knows pages."""

    title: str
    level: int
    offset: int
    page: Optional[int] = None


@dataclass(frozen=True)
class ParsedDocument:
    markdown: str
    parser: str
    page_count: int = 1
    tables: list[ParsedTable] = field(default_factory=list)
    #: Page by page, when the parser knows where pages start. Empty for text and HTML.
    pages: list[ParsedPage] = field(default_factory=list)
    #: The parser's own lossless form (Docling's JSON), for tools that need more than the Markdown.
    structured: Optional[dict[str, Any]] = None
    #: The headings, in reading order: how a reader finds a section without reading everything before it.
    outline: list[OutlineEntry] = field(default_factory=list)

    @property
    def text_chars(self) -> int:
        """Letters and digits the document holds: how much was read, without the table padding and image links."""
        return sum(c.isalnum() for c in IMAGE_LINK.sub("", self.markdown))


class OwnerKind(str, Enum):
    KNOWLEDGE_BASE = "knowledge_base"
    CONVERSATION = "conversation"


@dataclass(frozen=True)
class DocumentOwner:
    """What holds a document. The caller resolves it with its own access rules before handing it over."""

    account_id: str
    kind: OwnerKind
    owner_id: str

    @property
    def pk(self) -> str:
        return f"DocumentOwner#{self.kind.value}#{self.owner_id}"


class DocumentStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"
    DELETING = "deleting"


#: A worker may take a document in these states; the reaper looks at them too.
IN_FLIGHT = (DocumentStatus.PENDING, DocumentStatus.PARSING, DocumentStatus.INDEXING)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def safe_filename(filename: str) -> str:
    return SAFE_FILENAME.sub("_", filename).strip("._") or "file"


class Document(BaseModel):
    document_id: str = Field(default_factory=lambda: str(uuid4()))
    account_id: str
    owner_kind: OwnerKind
    owner_id: str
    filename: str
    content_type: str = ""
    size_bytes: int = 0
    #: sha256 of the original: the same file uploaded again is the same document.
    content_hash: str = ""
    #: What the uploader said about it; a knowledge base reads it with the content.
    metadata: str = ""
    #: The page a crawled document was found at.
    source_url: str = ""
    status: DocumentStatus = DocumentStatus.PENDING
    parser: str = ""
    parser_version: int = 0
    page_count: int = 0
    table_count: int = 0
    text_chars: int = 0
    markdown_chars: int = 0
    attempts: int = 0
    #: Epoch seconds until which a worker holds the document; 0 when none does.
    lease_expires_at: int = 0
    error: str = ""
    #: For an owner whose documents go out with a message (a conversation): 0 until it is sent, then when (epoch
    #: seconds). None for owners that don't attach documents (a knowledge base) and documents from before attaching.
    attached_at: Optional[int] = None
    created_by: str = ""
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    @property
    def owner(self) -> DocumentOwner:
        return DocumentOwner(self.account_id, self.owner_kind, self.owner_id)

    @property
    def pk(self) -> str:
        return self.owner.pk

    @property
    def sk(self) -> str:
        return f"Document#{self.document_id}"

    @property
    def prefix(self) -> str:
        """Where everything the document has lives in the bucket: deleting it is deleting this prefix."""
        return f"{self.account_id}/{self.owner_kind.value}/{self.owner_id}/{self.document_id}/"

    @property
    def original_key(self) -> str:
        return f"{self.prefix}original/{safe_filename(self.filename)}"

    @property
    def unsent(self) -> bool:
        return self.attached_at == 0

    def lease_lapsed(self, now: int) -> bool:
        return self.lease_expires_at <= now

    def to_dynamo_item(self) -> dict[str, Any]:
        item = self.model_dump(mode="json")
        item.update(pk=self.pk, sk=self.sk, entity_type="Document")
        return item

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "Document":
        fields = {key: value for key, value in item.items() if key in cls.model_fields}
        return cls.model_validate(fields)


class DocumentResponse(BaseModel):
    document_id: str
    owner_kind: OwnerKind
    owner_id: str
    filename: str
    content_type: str
    size_bytes: int
    metadata: str
    source_url: str
    status: DocumentStatus
    parser: str
    page_count: int
    table_count: int
    text_chars: int
    error: str
    created_by: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, document: Document) -> "DocumentResponse":
        return cls.model_validate(document.model_dump(include=set(cls.model_fields)))
