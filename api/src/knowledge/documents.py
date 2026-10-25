"""A knowledge base's documents: once read, a document is indexed as a page (chunks and vectors, through `PageIndex`,
so an upload is a page like any other); before it is deleted, its page is taken out.

Registered with `documents` at import (`knowledge/__init__.py` imports it), like `access.py` registers its resolver.
"""

import logging

from src.documents.follow_ups import register
from src.documents.models import Document, DocumentOwner, DocumentReadError, OwnerKind, ParsedDocument
from src.knowledge.models import KnowledgeBase, KnowledgeBaseStatus
from src.knowledge.repository import KnowledgeBaseRepository

log = logging.getLogger(__name__)


def owner_of(kb: KnowledgeBase) -> DocumentOwner:
    return DocumentOwner(account_id=kb.account_id, kind=OwnerKind.KNOWLEDGE_BASE, owner_id=kb.kb_id)


def page_url(document: Document) -> str:
    """The page a document is in the knowledge base: where it was found, or the upload's own address."""
    return document.source_url or f"file://{document.owner_id}/{document.filename}"


class KnowledgeBaseDocuments:
    async def after_parse(self, document: Document, reading: ParsedDocument) -> None:
        from src.knowledge.service import get_knowledge_base_service

        kb = self._kb(document)
        if kb is None:
            raise DocumentReadError("The knowledge base no longer exists")
        result = await get_knowledge_base_service().ingest_text_content(
            kb=kb, filename=document.filename, content=reading.markdown, metadata=document.metadata, source_url=page_url(document)
        )
        KnowledgeBaseRepository().update_stats(
            kb.account_id, kb.kb_id, total_pages=result.total_pages, total_chunks=result.total_chunks, total_vectors=result.total_chunks
        )

    def before_delete(self, document: Document) -> None:
        from src.knowledge.service import get_knowledge_base_service

        kb = self._kb(document)
        if kb is None:
            return  # the KB's delete took its namespace and pages
        get_knowledge_base_service().remove_page(kb, page_url(document), reason="document deleted")

    @staticmethod
    def _kb(document: Document) -> KnowledgeBase | None:
        kb = KnowledgeBaseRepository().find_in_account(document.account_id, document.owner_id)
        return kb if kb and kb.status != KnowledgeBaseStatus.DELETED else None


register(OwnerKind.KNOWLEDGE_BASE, KnowledgeBaseDocuments())
