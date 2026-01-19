"""
Knowledge Base service for business logic and orchestration.

Handles operations that span multiple repositories and external services.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.knowledge.models import KnowledgeBase, KnowledgeBaseStatus
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
