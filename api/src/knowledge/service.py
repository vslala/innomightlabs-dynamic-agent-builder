"""
Knowledge Base service for business logic and orchestration.

Handles operations that span multiple repositories and external services.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.knowledge.models import UPLOAD_SOURCE, ChunkingStrategy, KnowledgeBase, KnowledgeBaseStatus, KnowledgePage
from src.knowledge.repository import (
    KnowledgeBaseRepository,
    ContentChunkRepository,
    AgentKnowledgeBaseRepository,
    KnowledgePageRepository,
)

log = logging.getLogger(__name__)

SOFT_DELETE_TTL_DAYS = 30


@dataclass
class DeleteResult:
    """Result of a soft delete operation."""
    success: bool
    kb_id: str
    chunks_deleted: int = 0
    vectors_deleted: bool = False
    agents_unlinked: int = 0
    error: Optional[str] = None
    #: The vectors couldn't be deleted, so nothing was: the caller may try again, and the KB is as it was.
    retryable: bool = False


@dataclass
class UploadIngestResult:
    chunk_count: int
    #: Chunks that went through the embedding model: uploading the same file again embeds only what changed.
    vector_count: int
    #: What the knowledge base holds after the upload.
    total_pages: int
    total_chunks: int


class KnowledgeBaseService:
    """
    Service for knowledge base operations.

    Handles business logic that spans multiple repositories
    and external services (Pinecone).
    """

    def __init__(
        self,
        kb_repo: Optional[KnowledgeBaseRepository] = None,
        chunk_repo: Optional[ContentChunkRepository] = None,
        agent_kb_repo: Optional[AgentKnowledgeBaseRepository] = None,
    ):
        self.kb_repo = kb_repo or KnowledgeBaseRepository()
        self.chunk_repo = chunk_repo or ContentChunkRepository()
        self.agent_kb_repo = agent_kb_repo or AgentKnowledgeBaseRepository()
        self._pinecone = None

    @property
    def pinecone(self):
        """Lazy-load Pinecone client."""
        if self._pinecone is None:
            from src.vectorstore import get_pinecone_client
            self._pinecone = get_pinecone_client(validate=False)
        return self._pinecone

    def soft_delete(self, kb: KnowledgeBase) -> DeleteResult:
        """
        Soft delete a knowledge base with full cleanup.

        This method:
        1. Deletes the Pinecone namespace (all vectors). If that can't be done it stops: nothing else is deleted,
           the result is `retryable`, and the KB is as it was. Chunks are what record that vectors exist, so deleting
           them first would leave vectors nothing could find to delete.
        2. Deletes all content chunks, and the pages that list them, from DynamoDB
        3. Unlinks the KB from all agents, and forgets its shares
        4. Marks the KB as deleted with a TTL for auto-expiration (30 days)

        The KB record itself remains for 30 days to handle orphan cleanup,
        then DynamoDB TTL auto-deletes it. Callers have found the KB and
        checked the caller may delete it.

        Returns:
            DeleteResult with operation details
        """
        kb_id = kb.kb_id
        result = DeleteResult(success=False, kb_id=kb_id)

        if kb.status == KnowledgeBaseStatus.DELETED:
            result.error = f"Knowledge base {kb_id} is already deleted"
            return result

        try:
            result.vectors_deleted = self._delete_pinecone_namespace(kb_id)
        except Exception as e:
            log.error(f"Failed to delete Pinecone namespace for KB {kb_id}: {e}", exc_info=True)
        if not result.vectors_deleted:
            result.error = "The knowledge base's vectors couldn't be deleted, so nothing was deleted. Try again."
            result.retryable = True
            return result

        try:
            result.chunks_deleted = self.chunk_repo.delete_all_by_kb(kb_id)
            KnowledgePageRepository().delete_all_by_kb(kb_id)
        except Exception as e:
            log.error(f"Failed to delete chunks for KB {kb_id}: {e}", exc_info=True)

        try:
            result.agents_unlinked = self._unlink_from_all_agents(kb_id)
        except Exception as e:
            log.error(f"Failed to unlink agents for KB {kb_id}: {e}", exc_info=True)

        try:
            from src.iam.shares import ShareService

            ShareService().forget_resource(kb.account_id, "knowledge-base", kb_id)
        except Exception as e:
            log.error(f"Failed to forget shares of KB {kb_id}: {e}", exc_info=True)

        try:
            self._mark_as_deleted(kb)
            result.success = True
        except Exception as e:
            log.error(f"Failed to mark KB {kb_id} as deleted: {e}", exc_info=True)
            result.error = str(e)

        log.info(
            f"Soft deleted KB {kb_id}: "
            f"chunks={result.chunks_deleted}, "
            f"vectors={result.vectors_deleted}, "
            f"agents_unlinked={result.agents_unlinked}"
        )

        return result

    async def ingest_text_content(
        self,
        kb: KnowledgeBase,
        filename: str,
        content: str,
        metadata: Optional[str] = None,
    ) -> UploadIngestResult:
        """
        Ingest uploaded text content using the crawler chunking pipeline.

        Args:
            kb: Knowledge base
            filename: Original filename
            content: Text content
            metadata: Optional metadata to include in context

        Returns:
            UploadIngestResult with chunk and vector counts, and what the knowledge base holds after it
        """
        source_url = f"file://{kb.kb_id}/{filename}"
        metadata_text = (metadata or "").strip()
        title = f"{filename} — {metadata_text}" if metadata_text else filename
        content_to_chunk = f"Metadata:\n{metadata_text}\n\n{content}" if metadata_text else content

        # The crawler imports this package's models, so it's imported here rather than at the top
        from src.crawler.chunking import get_chunking_strategy
        from src.crawler.page_index import PageIndex, held
        from src.vectorstore import get_embeddings_service, get_pinecone_client

        chunk_data_list = get_chunking_strategy(ChunkingStrategy.HIERARCHICAL.value).chunk(
            content=content_to_chunk,
            source_url=source_url,
            page_title=title,
            sections=None,
        )
        index = PageIndex(
            kb.kb_id,
            vectors=get_pinecone_client(validate=True),
            embeddings=get_embeddings_service(),
            chunks=self.chunk_repo,
        )
        pages = index.load()
        embedded = 0
        if chunk_data_list:
            # A file uploaded again is the same page: only what changed in it is embedded, and what it lost is deleted
            page = pages.get(source_url) or KnowledgePage(kb_id=kb.kb_id, url=source_url, source=UPLOAD_SOURCE)
            written = await index.write(page, title, chunk_data_list)
            pages[source_url] = written.page
            embedded = written.embedded
        total_pages, total_chunks = held(pages.values())
        return UploadIngestResult(
            chunk_count=len(chunk_data_list), vector_count=embedded, total_pages=total_pages, total_chunks=total_chunks
        )

    def _delete_pinecone_namespace(self, kb_id: str) -> bool:
        """Whether the knowledge base's namespace is gone (or never was). Without Pinecone configured nothing could have
        been indexed, unless the KB has content: then it isn't known to be gone."""
        if self.pinecone._index is None:
            log.warning(f"Pinecone not configured, so the vectors of KB {kb_id} can't be deleted")
            return not self.chunk_repo.has_any(kb_id)
        deleted: bool = self.pinecone.delete_namespace(kb_id)
        return deleted

    def _unlink_from_all_agents(self, kb_id: str) -> int:
        """Unlink this KB from all agents."""
        links = self.agent_kb_repo.find_agents_for_kb(kb_id)
        unlinked = 0

        for link in links:
            if self.agent_kb_repo.unlink(link.agent_id, kb_id):
                unlinked += 1

        return unlinked

    def _mark_as_deleted(self, kb: KnowledgeBase) -> None:
        """Mark the KB as deleted with TTL."""
        now = datetime.now(timezone.utc)
        ttl_time = now + timedelta(days=SOFT_DELETE_TTL_DAYS)

        kb.status = KnowledgeBaseStatus.DELETED
        kb.deleted_at = now
        kb.updated_at = now
        kb.ttl = int(ttl_time.timestamp())
        kb.total_pages = 0
        kb.total_chunks = 0
        kb.total_vectors = 0

        self.kb_repo.save(kb)


_service: Optional[KnowledgeBaseService] = None


def get_knowledge_base_service() -> KnowledgeBaseService:
    """Get or create the knowledge base service singleton."""
    global _service
    if _service is None:
        _service = KnowledgeBaseService()
    return _service
