"""DocumentService: the one way to keep a file for an owner (store, read, record), read it back, and delete it.

The caller has checked who may use the owner; nothing here checks permissions. See docs/LLD-documents.md.
"""

import asyncio
import contextlib
import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from src.config import settings
from src.documents.follow_ups import FOLLOW_UPS
from src.documents.models import (
    IN_FLIGHT,
    Document,
    DocumentNotFound,
    DocumentOwner,
    DocumentReadError,
    DocumentStatus,
    OutlineEntry,
    OwnerKind,
    ParsedDocument,
    UnsupportedDocument,
)
from src.documents.outline import outline_from_markdown
from src.documents.parsers import DocumentParser
from src.documents.reader import PARSER_VERSION, parsers_for, read_document
from src.documents.repository import DocumentRepository
from src.documents.storage import DocumentStorage
from src.documents.tables import TableQuery, TableQueryError, describe_table, page_table, query_table

log = logging.getLogger(__name__)

#: How much of a document `read_markdown` returns at once, unless asked for less.
DEFAULT_READ_CHARS = 8000
MAX_READ_CHARS = 30000


class DocumentTooLarge(DocumentReadError):
    """Over `document_max_bytes`."""


class DocumentNotReady(DocumentReadError):
    """Asked for a reading that doesn't exist yet (still parsing) or never will (failed)."""


@dataclass(frozen=True)
class MarkdownSlice:
    text: str
    offset: int
    total_chars: int

    @property
    def next_offset(self) -> Optional[int]:
        end = self.offset + len(self.text)
        return end if end < self.total_chars else None


@dataclass(frozen=True)
class SearchHit:
    """A passage that matched: where it starts, the lines around the match, and the section it is in."""

    offset: int
    snippet: str
    section: str = ""


@dataclass(frozen=True)
class Section:
    title: str
    level: int
    offset: int
    end: int
    page: Optional[int] = None


@dataclass(frozen=True)
class SectionSlice:
    section: Section
    text: str
    #: Where in the section the text starts (0 is its heading); `next_offset` continues from here.
    offset: int
    section_chars: int

    @property
    def next_offset(self) -> Optional[int]:
        end = self.offset + len(self.text)
        return end if end < self.section_chars else None


@dataclass(frozen=True)
class Description:
    """What a document holds, so a reader picks the right way in without reading it first."""

    sections: list[Section]
    #: Pages with almost no text: scans, charts, signatures. Worth a look with `page_image`.
    weak_pages: list[int]
    tables: list[dict[str, Any]]


@dataclass(frozen=True)
class PagesSlice:
    pages: list[tuple[int, Optional[str]]]
    #: The page to ask for next when the characters allowed ran out before the pages asked for did.
    next_page: Optional[int]


#: Most characters `read_pages` returns at once: the pages asked for are cut short rather than filling the context.
MAX_PAGES_CHARS = 30000
MAX_PAGES = 10
#: Lines either side of a match in a search hit, and how many hits at most.
SEARCH_CONTEXT_LINES = 2
MAX_SEARCH_HITS = 10
SNIPPET_CHARS = 700


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentService:
    def __init__(
        self,
        repository: Optional[DocumentRepository] = None,
        storage: Optional[DocumentStorage] = None,
        parsers: Optional[list[DocumentParser]] = None,
    ) -> None:
        self.repository = repository or DocumentRepository()
        self.storage = storage or DocumentStorage()
        self.parsers = parsers

    # -- keeping a file -------------------------------------------------------------------------------------------

    def submit(
        self,
        owner: DocumentOwner,
        filename: str,
        data: bytes,
        *,
        created_by: str,
        content_type: str = "",
        metadata: str = "",
        source_url: str = "",
        sent_with_a_message: bool = False,
    ) -> Document:
        """Store the original and record the document as pending; `worker.launch` reads it in the background.

        The same file (name and content) uploaded again is the same document, left as it is. A changed file under the
        same name replaces it: same id, read again. `sent_with_a_message`: the owner attaches documents to messages
        (a conversation), so a new one waits to be sent (`attach`); `sweep_unsent` removes those never sent.
        """
        if not parsers_for(filename, self.parsers):
            raise UnsupportedDocument(f"'{filename}' is not a kind of file that can be read")
        if len(data) > settings.document_max_bytes:
            raise DocumentTooLarge(f"'{filename}' is over the {settings.document_max_bytes // (1024 * 1024)} MB limit")

        content_hash = hashlib.sha256(data).hexdigest()
        existing = self.repository.find_by_filename(owner, filename)
        unchanged = existing and existing.content_hash == content_hash and existing.metadata == metadata
        if existing and unchanged and existing.status in (DocumentStatus.READY, *IN_FLIGHT):
            return existing

        fields: dict[str, Any] = {
            "content_type": content_type,
            "size_bytes": len(data),
            "content_hash": content_hash,
            "metadata": metadata,
            "source_url": source_url,
            "status": DocumentStatus.PENDING,
            # A new file is read from scratch: nothing of the last reading carries over
            "parser": "",
            "parser_version": 0,
            "page_count": 0,
            "table_count": 0,
            "text_chars": 0,
            "markdown_chars": 0,
            "attempts": 0,
            "lease_expires_at": 0,
            "error": "",
            "created_by": created_by,
            "updated_at": _now(),
        }
        if existing:
            document = existing.model_copy(update=fields)
        else:
            document = Document(
                account_id=owner.account_id,
                owner_kind=owner.kind,
                owner_id=owner.owner_id,
                filename=filename,
                attached_at=0 if sent_with_a_message else None,
                **fields,
            )
        self.storage.put_original(document, data)
        return self.repository.save(document)

    async def process(self, owner: DocumentOwner, document_id: str) -> Optional[Document]:
        """Read a pending document and keep what was read. None when another worker holds it, or it is done or gone.

        A file no parser can read fails for good. Anything else (S3, the owner's follow-up) leaves it pending for the
        reaper to try again, up to `document_max_attempts`. A document already read by this parser version is not read
        again: the attempt picks up at the owner's follow-up (a KB's embedding being throttled, say).
        """
        document = self.repository.claim(owner, document_id, lease_seconds=settings.document_lease_seconds, now=int(time.time()))
        if document is None:
            return None
        # Reading and indexing a large file can outlast the lease: renew it while this worker is at it, so the reaper
        # never hands the document to a second worker as if this one had died
        heartbeat = asyncio.create_task(self._keep_lease(document))
        try:
            return await self._process(document)
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat

    async def _keep_lease(self, document: Document) -> None:
        lease = settings.document_lease_seconds
        while True:
            await asyncio.sleep(max(1, lease // 3))
            try:
                renewed = await asyncio.to_thread(self.repository.renew, document, lease_seconds=lease, now=int(time.time()))
            except Exception:
                log.warning("Couldn't renew the lease on document %s", document.document_id, exc_info=True)
                continue
            if not renewed:
                return

    async def _process(self, document: Document) -> Optional[Document]:
        try:
            if document.parser and document.parser_version == PARSER_VERSION:
                reading = self._stored_reading(document)
            else:
                reading = await read_document(self.storage.original(document), document.filename, parsers=self.parsers)
                self.storage.put_reading(document, reading)
                document = document.model_copy(update={
                    "parser": reading.parser,
                    "parser_version": PARSER_VERSION,
                    "page_count": reading.page_count,
                    "table_count": len(reading.tables),
                    "text_chars": reading.text_chars,
                    "markdown_chars": len(reading.markdown),
                })
            follow_up = FOLLOW_UPS.get(document.owner_kind)
            if follow_up is not None:
                indexing = self.repository.save_in_flight(self._at(document, status=DocumentStatus.INDEXING))
                if indexing is None:
                    return None
                await follow_up.after_parse(indexing, reading)
            return self.repository.save_in_flight(
                self._at(document, status=DocumentStatus.READY, lease_expires_at=0, error="")
            )
        except DocumentReadError as exc:
            log.warning("Document %s couldn't be read: %s", document.document_id, exc)
            return self.repository.save_in_flight(
                self._at(document, status=DocumentStatus.FAILED, error=str(exc)[:500], lease_expires_at=0)
            )
        except Exception as exc:
            log.error("Processing document %s failed", document.document_id, exc_info=True)
            gave_up = document.attempts >= settings.document_max_attempts
            return self.repository.save_in_flight(self._at(
                document,
                status=DocumentStatus.FAILED if gave_up else DocumentStatus.PENDING,
                error=f"{exc.__class__.__name__}: {exc}"[:500],
                lease_expires_at=0,
            ))

    def requeue_stale(self, launch: Callable[[Document], None]) -> int:
        """The reaper: a document whose worker died (lease lapsed) is launched again, or failed once it has used its
        attempts. Returns how many were failed."""
        now = int(time.time())
        failed = 0
        for document in self.repository.in_flight():
            if not document.lease_lapsed(now):
                continue
            if document.attempts >= settings.document_max_attempts:
                error = document.error or "Reading the document kept being interrupted. Upload it again to retry."
                if self.repository.save_in_flight(self._at(document, status=DocumentStatus.FAILED, error=error)):
                    failed += 1
            else:
                launch(document)
        return failed

    def attach(self, owner: DocumentOwner, document_ids: list[str]) -> list[Document]:
        """The documents a message is sent with, marked sent. Every id must be the owner's and not being deleted, or
        none is marked. A document already sent can go out again with a later message."""
        documents = []
        for document_id in document_ids:
            document = self.get(owner, document_id)
            if document is None:
                raise DocumentNotFound(f"There is no document {document_id} here to attach.")
            documents.append(document)
        now = int(time.time())
        for document in documents:
            if document.unsent:
                self.repository.mark_attached(document, now=now)
        return documents

    def unsent(self, owner: DocumentOwner) -> list[Document]:
        """Uploaded and not yet sent with a message: what the composer shows."""
        return [document for document in self.documents(owner) if document.unsent]

    def sweep_unsent(self, kind: OwnerKind, *, older_than_seconds: int) -> int:
        """Delete the owner kind's documents uploaded more than `older_than_seconds` ago and never sent. Returns how
        many. One that can't be deleted now is left for the next sweep."""
        cutoff = _now().timestamp() - older_than_seconds
        removed = 0
        for document in self.repository.unsent(kind):
            if document.created_at.timestamp() >= cutoff:
                continue
            try:
                self.delete(document)
                removed += 1
            except Exception:
                log.warning("Couldn't sweep unsent document %s", document.document_id, exc_info=True)
        return removed

    def retry(self, document: Document) -> Document:
        """Try a failed document again: from its stored original, or from its stored reading when only the owner's
        follow-up failed."""
        return self.repository.save(
            self._at(document, status=DocumentStatus.PENDING, attempts=0, error="", lease_expires_at=0)
        )

    # -- reading it back ------------------------------------------------------------------------------------------

    def get(self, owner: DocumentOwner, document_id: str) -> Optional[Document]:
        document = self.repository.get(owner, document_id)
        return document if document and document.status != DocumentStatus.DELETING else None

    def documents(self, owner: DocumentOwner) -> list[Document]:
        return [document for document in self.repository.list_by_owner(owner) if document.status != DocumentStatus.DELETING]

    def read_markdown(self, document: Document, *, offset: int = 0, length: int = DEFAULT_READ_CHARS) -> MarkdownSlice:
        markdown = self.storage.markdown(self._ready(document))
        offset = max(0, offset)
        length = max(1, min(length, MAX_READ_CHARS))
        return MarkdownSlice(text=markdown[offset:offset + length], offset=offset, total_chars=len(markdown))

    def read_page(self, document: Document, number: int) -> Optional[str]:
        return self.storage.page_markdown(self._ready(document), number)

    def read_pages(self, document: Document, first: int, last: int) -> PagesSlice:
        """Pages `first` to `last` (up to `MAX_PAGES`), stopping at `MAX_PAGES_CHARS`; the first page is always given."""
        ready = self._ready(document)
        first = max(1, first)
        last = min(last, first + MAX_PAGES - 1, max(document.page_count, first))
        pages: list[tuple[int, Optional[str]]] = []
        used = 0
        for number in range(first, last + 1):
            markdown = self.storage.page_markdown(ready, number)
            used += len(markdown or "")
            if pages and used > MAX_PAGES_CHARS:
                return PagesSlice(pages=pages, next_page=number)
            pages.append((number, markdown))
        return PagesSlice(pages=pages, next_page=None)

    def describe(self, document: Document) -> Description:
        """The sections, the pages with little text and the tables, from what was kept when the file was read. A
        document read before outlines were kept still has its headings, found again in the Markdown."""
        ready = self._ready(document)
        stored = self.storage.outline(ready)
        if stored is None:
            headings = outline_from_markdown(self.storage.markdown(ready))
            return Description(sections=self._sections(headings, document.markdown_chars), weak_pages=[], tables=[])
        headings = [OutlineEntry(h["title"], h["level"], h["offset"], h.get("page")) for h in stored["headings"]]
        return Description(
            sections=self._sections(headings, document.markdown_chars), weak_pages=stored["weak_pages"], tables=stored["tables"]
        )

    def read_section(
        self, document: Document, number: int, *, offset: int = 0, length: int = DEFAULT_READ_CHARS
    ) -> SectionSlice:
        """Section `number` (from 1, as `describe` lists them): its heading and what follows, up to the next heading
        of its level or above. `offset` counts from the section's start."""
        sections = self.describe(document).sections
        if not 1 <= number <= len(sections):
            raise DocumentReadError(f"'{document.filename}' has {len(sections)} section(s), numbered from 1")
        section = sections[number - 1]
        markdown = self.storage.markdown(document)[section.offset:section.end]
        offset = max(0, offset)
        length = max(1, min(length, MAX_READ_CHARS))
        return SectionSlice(section=section, text=markdown[offset:offset + length], offset=offset, section_chars=len(markdown))

    def describe_table(self, document: Document, number: int) -> dict[str, Any]:
        return describe_table(self._table(document, number), number)

    def read_table(
        self, document: Document, number: int, *, from_row: int = 1, max_rows: int = 50, columns: Optional[list[str]] = None
    ) -> dict[str, Any]:
        return page_table(self._table(document, number), from_row=from_row, max_rows=max_rows, columns=columns)

    def query_table(self, document: Document, number: int, query: TableQuery) -> dict[str, Any]:
        return query_table(self._table(document, number), query)

    def page_image(self, document: Document, number: int) -> Optional[bytes]:
        return self.storage.page_image(self._ready(document), number)

    def search(self, document: Document, query: str, *, limit: int = MAX_SEARCH_HITS) -> list[SearchHit]:
        """The passages that match the query (any case), best first: those holding every word, then those holding
        most. Each is the matching line with a few lines either side, and the section it is in."""
        words = [word.lower() for word in query.split()]
        if not words:
            return []
        markdown = self.storage.markdown(self._ready(document))
        lines = markdown.splitlines(keepends=True)
        starts = [0]
        for line in lines:
            starts.append(starts[-1] + len(line))
        scored = []
        for index, line in enumerate(lines):
            lowered = line.lower()
            found = sum(word in lowered for word in words)
            if found:
                scored.append((-found, index))
        scored.sort()

        hits: list[tuple[int, SearchHit]] = []  # (line index, hit)
        covered: list[range] = []
        sections = self.describe(document).sections
        for _, index in scored:
            if len(hits) >= max(1, min(limit, MAX_SEARCH_HITS)):
                break
            first, last = max(0, index - SEARCH_CONTEXT_LINES), min(len(lines), index + SEARCH_CONTEXT_LINES + 1)
            if any(index in span for span in covered):
                continue
            covered.append(range(first, last))
            snippet = "".join(lines[first:last]).strip()[:SNIPPET_CHARS]
            section = next((s.title for s in reversed(sections) if s.offset <= starts[index]), "")
            hits.append((index, SearchHit(offset=starts[first], snippet=snippet, section=section)))
        return [hit for _, hit in hits]

    # -- deleting -------------------------------------------------------------------------------------------------

    def delete(self, document: Document) -> None:
        """The owner's part first (a KB's chunks and vectors), then the bucket, then the row: the row records what the
        bucket holds, so it goes last. A failure stops here and the delete can be run again."""
        document = self.repository.save(self._at(document, status=DocumentStatus.DELETING, lease_expires_at=0))
        follow_up = FOLLOW_UPS.get(document.owner_kind)
        if follow_up is not None:
            follow_up.before_delete(document)
        self.storage.delete(document)
        self.repository.delete(document)

    def delete_all(self, owner: DocumentOwner) -> int:
        """Every document the owner holds, for an owner that is going away and has already removed what it built from
        them (a KB's namespace). The bucket, then the rows."""
        documents = self.repository.list_by_owner(owner)
        for document in documents:
            self.repository.save(self._at(document, status=DocumentStatus.DELETING, lease_expires_at=0))
            self.storage.delete(document)
            self.repository.delete(document)
        return len(documents)

    def _stored_reading(self, document: Document) -> ParsedDocument:
        """The reading kept for a document, as a follow-up needs it: the Markdown and what was counted. Pages and
        tables stay in the bucket, read by number."""
        return ParsedDocument(markdown=self.storage.markdown(document), parser=document.parser, page_count=document.page_count)

    def _table(self, document: Document, number: int) -> list[list[str]]:
        rows = self.storage.table(self._ready(document), number)
        if rows is None:
            raise TableQueryError(f"'{document.filename}' has {document.table_count} table(s), numbered from 1")
        return rows

    @staticmethod
    def _sections(headings: list[OutlineEntry], total_chars: int) -> list[Section]:
        """Each heading's section runs to the next heading of its level or above, or the end."""
        sections = []
        for index, heading in enumerate(headings):
            end = next((h.offset for h in headings[index + 1:] if h.level <= heading.level), total_chars)
            sections.append(Section(heading.title, heading.level, heading.offset, end, heading.page))
        return sections

    def _ready(self, document: Document) -> Document:
        if document.status not in (DocumentStatus.READY, DocumentStatus.INDEXING):
            raise DocumentNotReady(f"'{document.filename}' is {document.status.value}" + (f": {document.error}" if document.error else ""))
        return document

    @staticmethod
    def _at(document: Document, **changes: object) -> Document:
        return document.model_copy(update={**changes, "updated_at": _now()})


_service: Optional[DocumentService] = None


def get_document_service() -> DocumentService:
    global _service
    if _service is None:
        _service = DocumentService()
    return _service
