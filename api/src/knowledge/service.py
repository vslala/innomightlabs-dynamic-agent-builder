"""
Knowledge Base service for business logic and orchestration.

Handles operations that span multiple repositories and external services.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.knowledge.models import KnowledgeBase, KnowledgeBaseStatus, ContentChunk, ChunkingStrategy
from src.crawler.chunking import get_chunking_strategy
from src.crawler.worker import generate_chunk_id
from src.vectorstore.pinecone_client import VectorRecord, VectorMetadata
from src.knowledge.repository import (
    KnowledgeBaseRepository,
    ContentChunkRepository,
    AgentKnowledgeBaseRepository,
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


@dataclass
class UploadIngestResult:
    chunk_count: int
    vector_count: int


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

    def soft_delete(self, kb_id: str, user_email: str) -> DeleteResult:
        """
        Soft delete a knowledge base with full cleanup.

        This method:
        1. Marks the KB as deleted with a TTL for auto-expiration (30 days)
        2. Immediately deletes all content chunks from DynamoDB
        3. Immediately deletes the Pinecone namespace (all vectors)
        4. Unlinks the KB from all agents

        The KB record itself remains for 30 days to handle orphan cleanup,
        then DynamoDB TTL auto-deletes it.

        Args:
            kb_id: Knowledge base ID
            user_email: User email (owner)

        Returns:
            DeleteResult with operation details
        """
        result = DeleteResult(success=False, kb_id=kb_id)

        kb = self.kb_repo.find_by_id(kb_id, user_email)
        if not kb:
            result.error = f"Knowledge base {kb_id} not found"
            return result

        if kb.status == KnowledgeBaseStatus.DELETED:
            result.error = f"Knowledge base {kb_id} is already deleted"
            return result

        try:
            result.vectors_deleted = self._delete_pinecone_namespace(kb_id)
        except Exception as e:
            log.error(f"Failed to delete Pinecone namespace for KB {kb_id}: {e}", exc_info=True)

        try:
            result.chunks_deleted = self.chunk_repo.delete_all_by_kb(kb_id)
        except Exception as e:
            log.error(f"Failed to delete chunks for KB {kb_id}: {e}", exc_info=True)

        try:
            result.agents_unlinked = self._unlink_from_all_agents(kb_id)
        except Exception as e:
            log.error(f"Failed to unlink agents for KB {kb_id}: {e}", exc_info=True)

        try:
            self._mark_as_deleted(kb, user_email)
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
        user_email: str,
        filename: str,
        content: str,
        metadata: Optional[str] = None,
    ) -> UploadIngestResult:
        """
        Ingest uploaded text content using the crawler chunking pipeline.

        Args:
            kb: Knowledge base
            user_email: Owner email
            filename: Original filename
            content: Text content
            metadata: Optional metadata to include in context

        Returns:
            UploadIngestResult with chunk and vector counts
        """
        source_url = f"file://{kb.kb_id}/{filename}"
        metadata_text = (metadata or "").strip()
        title = f"{filename} — {metadata_text}" if metadata_text else filename

        content_to_chunk = content
        if metadata_text:
            content_to_chunk = f"Metadata:\n{metadata_text}\n\n{content}"

        chunking_strategy = get_chunking_strategy(ChunkingStrategy.HIERARCHICAL.value)
        chunk_data_list = chunking_strategy.chunk(
            content=content_to_chunk,
            source_url=source_url,
            page_title=title,
            sections=None,
        )

        if not chunk_data_list:
            return UploadIngestResult(chunk_count=0, vector_count=0)

        from src.vectorstore import get_embeddings_service, get_pinecone_client

        embeddings = get_embeddings_service()
        pinecone = get_pinecone_client(validate=True)

        texts = [chunk.content for chunk in chunk_data_list]
        embedding_results = await embeddings.embed_texts_async(texts)

        # Build mapping from old random UUID to chunk info for parent_chunk_id resolution
        old_id_to_info: dict[str, tuple[int, int]] = {}
        for chunk_data in chunk_data_list:
            old_id_to_info[chunk_data.chunk_id] = (chunk_data.chunk_index, chunk_data.level)

        chunks: list[ContentChunk] = []
        vectors: list[VectorRecord] = []

        for chunk_data, emb_result in zip(chunk_data_list, embedding_results):
            chunk_id = generate_chunk_id(
                kb_id=kb.kb_id,
                source_url=source_url,
                chunk_index=chunk_data.chunk_index,
                level=chunk_data.level,
            )

            parent_chunk_id = None
            if chunk_data.parent_chunk_id and chunk_data.parent_chunk_id in old_id_to_info:
                parent_index, parent_level = old_id_to_info[chunk_data.parent_chunk_id]
                parent_chunk_id = generate_chunk_id(
                    kb_id=kb.kb_id,
                    source_url=source_url,
                    chunk_index=parent_index,
                    level=parent_level,
                )

            chunk = ContentChunk(
                chunk_id=chunk_id,
                kb_id=kb.kb_id,
                source_url=source_url,
                page_title=title,
                chunk_index=chunk_data.chunk_index,
                content=chunk_data.content,
                word_count=chunk_data.word_count,
                parent_chunk_id=parent_chunk_id,
                level=chunk_data.level,
            )
            chunks.append(chunk)

            vectors.append(
                VectorRecord(
                    id=chunk_id,
                    values=emb_result.embedding,
                    metadata=VectorMetadata(
                        kb_id=kb.kb_id,
                        chunk_id=chunk_id,
                        source_url=source_url,
                        page_title=title,
                        chunk_index=chunk_data.chunk_index,
                        level=chunk_data.level,
                        word_count=chunk_data.word_count,
                    ),
                )
            )

        self.chunk_repo.batch_save(chunks)
        pinecone.upsert(vectors, kb.kb_id)

        return UploadIngestResult(
            chunk_count=len(chunks),
            vector_count=len(vectors),
        )

    def _delete_pinecone_namespace(self, kb_id: str) -> bool:
        """Delete the Pinecone namespace for this KB."""
        if self.pinecone._index is None:
            log.warning("Pinecone not configured, skipping namespace deletion")
            return False

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

    def _mark_as_deleted(self, kb: KnowledgeBase, user_email: str) -> None:
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
