"""A knowledge base's pages in DynamoDB and Pinecone, written in an order a crash or a failed call can't turn into
wrong answers.

Search returns a chunk's text only while DynamoDB has the chunk, so what DynamoDB has is what agents can say. Every
change to a page therefore goes the same way:

1. Embed the chunks the page didn't have (`page_chunks.py` names chunks by what they say).
2. List everything the write touches as pending (`KnowledgePage.pending_ids`): the chunks it writes and the ones it
   deletes. A write that stops anywhere is then found, and finished, by the next one.
3. Write their vectors (`upsert` raises if it didn't happen), then their chunks.
4. Delete the chunks the page no longer has. This is the commit point: from here, search can't return the old text.
5. Record the page as it is now, then delete the old vectors. A delete that fails leaves inert vectors, kept on the
   page as orphans and deleted by a later write.

Only `remove` deletes a whole page, and only because the site said it's gone.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlparse

from src.crawler.chunking import ContentChunkData
from src.web_pages.fetch import same_site
from src.crawler.page_chunks import prepare_page, vectors_for
from src.knowledge.models import UPLOAD_SOURCE, KnowledgePage, KnowledgePageState
from src.knowledge.repository import ContentChunkRepository, CrawlJobRepository, KnowledgePageRepository
from src.vectorstore.embeddings import EmbeddingProvider
from src.vectorstore.pinecone_client import PineconeClient


def address_rank(url: str) -> tuple[bool, bool, int, str]:
    """Which of two addresses for one page is kept: no query string, then not the bare domain (discovery writes the
    root as "/"), then the shorter."""
    parsed = urlparse(url)
    return bool(parsed.query), parsed.path == "", len(url), url


def held(pages: Iterable[KnowledgePage]) -> tuple[int, int]:
    """What a knowledge base holds, as its stats count it: the pages that have chunks, and their chunks."""
    with_chunks = [page for page in pages if page.chunk_ids]
    return len(with_chunks), sum(len(page.chunk_ids) for page in with_chunks)


def _owner(url: str, sources: set[str]) -> str:
    if url.startswith("file://"):
        return UPLOAD_SOURCE
    under = [source for source in sources if url.startswith(source)]
    on_site = [source for source in sources if same_site(url, source)]
    # The narrowest source it's under, else the broadest on its site
    return max(under, key=len) if under else min(on_site, key=len) if on_site else ""


@dataclass(frozen=True)
class Written:
    page: KnowledgePage
    chunks: int
    #: Chunks that went through the embedding model; the rest were unchanged.
    embedded: int
    #: Chunks the page no longer had.
    removed: int


class PageIndex:
    def __init__(
        self,
        kb_id: str,
        *,
        vectors: PineconeClient,
        embeddings: EmbeddingProvider,
        chunks: ContentChunkRepository | None = None,
        pages: KnowledgePageRepository | None = None,
    ) -> None:
        self.kb_id = kb_id
        self.vectors = vectors
        self.embeddings = embeddings
        self.chunks = chunks or ContentChunkRepository()
        self.pages = pages or KnowledgePageRepository()

    def load(self) -> dict[str, KnowledgePage]:
        """The knowledge base's pages by URL. The first time, its chunks from before pages were kept get pages."""
        if not self.pages.adopted(self.kb_id):
            self._adopt()
        return {page.url: page for page in self.pages.list_by_kb(self.kb_id)}

    def _adopt(self) -> None:
        """Give each URL that has chunks but no page one, so its chunks can be found and cleaned like any page's.

        An uploaded file is the uploads'. A page is the crawl source it falls under (the longest one, if several do),
        else one on its site; anything else belongs to no crawl, so no crawl will verify it. Safe to run again: pages
        that exist are left alone.
        """
        sources = {job.config.source_url for job in CrawlJobRepository().find_all_by_kb(self.kb_id, limit=None)}
        paged = {page.url for page in self.pages.list_by_kb(self.kb_id)}
        by_url: dict[str, list[str]] = {}
        for chunk in self.chunks.find_all_by_kb(self.kb_id):
            if chunk.source_url not in paged:
                by_url.setdefault(chunk.source_url, []).append(chunk.chunk_id)
        for url, chunk_ids in by_url.items():
            self.pages.save(KnowledgePage(kb_id=self.kb_id, url=url, source=_owner(url, sources), chunk_ids=chunk_ids))
        self.pages.mark_adopted(self.kb_id)

    async def write(self, page: KnowledgePage, title: str, chunk_data: list[ContentChunkData], *, job_id: str = "") -> Written:
        """The page as read now: what changed is embedded and written, what it no longer has is deleted."""
        # A pending chunk the page still has isn't committed, so it's written again
        prepared = prepare_page(self.kb_id, page.url, title, chunk_data, set(page.chunk_ids))
        changed = prepared.new
        kept = {chunk.chunk_id for chunk in prepared.chunks}
        dropped = [chunk_id for chunk_id in dict.fromkeys(page.chunk_ids + page.pending_ids) if chunk_id not in kept]

        if changed or dropped:
            embedded = await self.embeddings.embed_texts_async([chunk.content for chunk in changed]) if changed else []
            # Until the page is saved as it is now, everything this write touches is pending: what it writes, and what
            # it deletes. Only chunks it leaves alone stay committed, so a write that stops anywhere is found next time.
            page = self._pending(page, keep=kept, touching=[chunk.chunk_id for chunk in changed] + dropped)
            if changed:
                self.vectors.upsert(vectors_for(changed, embedded), self.kb_id)
                self.chunks.batch_save(changed)
            if dropped:
                self.chunks.delete_by_ids(self.kb_id, dropped)

        page = self.pages.save(page.model_copy(update={
            "chunk_ids": [chunk.chunk_id for chunk in prepared.chunks],
            "pending_ids": [],
            "state": KnowledgePageState.LIVE,
            "duplicate_of": "",
            "title": title,
            "last_seen_job": job_id,
            "last_read_at": datetime.now(timezone.utc),
            "consecutive_failures": 0,
            "reason": "",
        }))
        page = self._delete_vectors(page, dropped)
        return Written(page=page, chunks=len(prepared.chunks), embedded=len(changed), removed=len(dropped))

    def remove(self, page: KnowledgePage, *, reason: str, job_id: str) -> KnowledgePage:
        """Take a page the site said is gone out of the knowledge base: its chunks first, so search stops returning it."""
        return self._empty(page, {"state": KnowledgePageState.GONE, "reason": reason, "last_seen_job": job_id})

    def alias(self, page: KnowledgePage, *, of: KnowledgePage, text_hash: str, job_id: str) -> KnowledgePage:
        """The page says what `of` says: it keeps no chunks of its own, so the passage isn't in search twice."""
        return self._empty(page, {
            "state": KnowledgePageState.DUPLICATE,
            "duplicate_of": of.url,
            "text_hash": text_hash,
            "last_seen_job": job_id,
            "consecutive_failures": 0,
            "reason": "",
        })

    def repoint(self, page: KnowledgePage, *, to: KnowledgePage) -> KnowledgePage:
        """A duplicate whose page was itself made a duplicate of `to` now stands behind `to`."""
        return self.pages.save(page.model_copy(update={"duplicate_of": to.url}))

    def _empty(self, page: KnowledgePage, changes: dict[str, object]) -> KnowledgePage:
        """Delete the page's chunks and vectors and record why it has none. Chunks first: search returns a vector's text
        only while its chunk exists."""
        dropped = list(dict.fromkeys(page.chunk_ids + page.pending_ids))
        if dropped:
            page = self._pending(page, keep=set(), touching=dropped)
            self.chunks.delete_by_ids(self.kb_id, dropped)
        page = self.pages.save(page.model_copy(update={
            "chunk_ids": [],
            "pending_ids": [],
            "last_read_at": datetime.now(timezone.utc),
            **changes,
        }))
        return self._delete_vectors(page, dropped)

    def seen(self, page: KnowledgePage, *, job_id: str, etag: str | None, last_modified: str | None) -> KnowledgePage:
        """Read again and unchanged: only when it was read moves (and orphans left by an old write are retried)."""
        page = self.pages.save(page.model_copy(update={
            "last_seen_job": job_id,
            "last_read_at": datetime.now(timezone.utc),
            "etag": etag,
            "last_modified": last_modified,
        }))
        return self._delete_vectors(page, [])

    def failed(self, page: KnowledgePage, *, reason: str, job_id: str) -> KnowledgePage:
        """A read that proves nothing: the page keeps the chunks of its last good read."""
        return self.pages.save(page.model_copy(update={
            "state": KnowledgePageState.FAILING,
            "last_seen_job": job_id,
            "consecutive_failures": page.consecutive_failures + 1,
            "reason": reason,
        }))

    def _pending(self, page: KnowledgePage, *, keep: set[str], touching: list[str]) -> KnowledgePage:
        """Before a change: the committed chunks it keeps stay committed, and everything it touches (with anything an
        earlier change left pending) is pending."""
        return self.pages.save(page.model_copy(update={
            "chunk_ids": [chunk_id for chunk_id in page.chunk_ids if chunk_id in keep],
            "pending_ids": list(dict.fromkeys(page.pending_ids + touching)),
        }))

    def _delete_vectors(self, page: KnowledgePage, chunk_ids: list[str]) -> KnowledgePage:
        """Delete these vectors and the page's orphans; what still can't be deleted stays an orphan."""
        doomed = list(dict.fromkeys(chunk_ids + page.orphan_vector_ids))
        if not doomed:
            return page
        not_deleted = self.vectors.delete_by_ids(doomed, self.kb_id)
        if not_deleted == page.orphan_vector_ids:
            return page
        return self.pages.save(page.model_copy(update={"orphan_vector_ids": not_deleted}))
