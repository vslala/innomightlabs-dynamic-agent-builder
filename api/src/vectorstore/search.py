"""
Semantic search service for knowledge bases.

Combines the configured embedding provider and Pinecone for semantic search
with content retrieval from DynamoDB.
"""

import logging
from typing import Optional
from dataclasses import dataclass

from src.vectorstore.embeddings import EmbeddingProvider, get_embeddings_service
from src.vectorstore.pinecone_client import PineconeClient, QueryResult, get_pinecone_client
from src.knowledge.models import ContentChunk
from src.knowledge.repository import ContentChunkRepository

log = logging.getLogger(__name__)

#: How many times `top_k` candidates to ask the index for: some are dropped as duplicates, or as having no text.
OVERFETCH = 3


@dataclass
class SearchResult:
    """A search result with full content."""
    chunk_id: str
    content: str
    source_url: str
    page_title: str
    score: float
    level: int  # 0=document, 1=section, 2=paragraph
    word_count: int
    section_heading: str = ""


@dataclass
class SearchResponse:
    """Response from a semantic search."""
    results: list[SearchResult]
    query: str
    kb_id: str


class SemanticSearch:
    """
    Semantic search service for knowledge bases.

    Workflow:
    1. Embed the query using the configured provider
    2. Search Pinecone for similar vectors
    3. Retrieve full content from DynamoDB
    4. Return enriched results
    """

    def __init__(
        self,
        embeddings: EmbeddingProvider | None = None,
        pinecone: Optional[PineconeClient] = None,
        chunk_repo: Optional[ContentChunkRepository] = None,
    ):
        """
        Initialize the semantic search service.

        Args:
            embeddings: Embeddings service (default: singleton)
            pinecone: Pinecone client (default: singleton)
            chunk_repo: Content chunk repository (default: new instance)
        """
        self.embeddings = embeddings or get_embeddings_service()
        self.pinecone = pinecone or get_pinecone_client()
        self.chunk_repo = chunk_repo or ContentChunkRepository()

    async def search(
        self,
        query: str,
        kb_id: str,
        top_k: int = 5,
        min_score: float = 0.0,
        level_filter: Optional[list[int]] = None,
    ) -> SearchResponse:
        """
        Search a knowledge base for relevant content.

        Args:
            query: Search query text
            kb_id: Knowledge base ID
            top_k: Number of results to return
            min_score: Minimum similarity score threshold
            level_filter: Optional filter by chunk level (0, 1, 2)

        Returns:
            SearchResponse with ranked results
        """
        # Step 1: Embed the query
        try:
            embedding_result = await self.embeddings.embed_text_async(query)
            query_vector = embedding_result.embedding
        except Exception as e:
            log.error(f"Failed to embed query: {e}")
            return SearchResponse(results=[], query=query, kb_id=kb_id)

        # Step 2: Build filter if specified
        pinecone_filter = None
        if level_filter:
            pinecone_filter = {"level": {"$in": level_filter}}

        # Step 3: Query Pinecone, for more than top_k: some will be dropped as duplicates or as scoring too low
        response = self.pinecone.query(
            vector=query_vector,
            kb_id=kb_id,
            top_k=top_k * OVERFETCH,
            filter=pinecone_filter,
        )

        # Step 4: The text of what was found, from DynamoDB
        results = self._distinct(response.results, self._chunks_of(response.results, kb_id), top_k, min_score)
        return SearchResponse(results=results, query=query, kb_id=kb_id)

    async def search_multiple_kbs(
        self,
        query: str,
        kb_ids: list[str],
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        """
        Search across multiple knowledge bases.

        Args:
            query: Search query text
            kb_ids: List of knowledge base IDs
            top_k: Total number of results to return

        Returns:
            Combined list of results sorted by score
        """
        # Embed query once
        try:
            embedding_result = await self.embeddings.embed_text_async(query)
            query_vector = embedding_result.embedding
        except Exception as e:
            log.error(f"Failed to embed query: {e}")
            return []

        # Query all KBs, for more than top_k: some will be dropped as duplicates or as scoring too low
        found = self.pinecone.query_multiple_kbs(vector=query_vector, kb_ids=kb_ids, top_k=top_k * OVERFETCH)
        chunks: dict[str, ContentChunk] = {}
        for kb_id in {r.metadata.kb_id for r in found}:
            chunks |= self._chunks_of(found, kb_id)
        return self._distinct(found, chunks, top_k, min_score)

    def _chunks_of(self, found: list[QueryResult], kb_id: str) -> dict[str, ContentChunk]:
        """The chunks of this knowledge base's vectors that still exist, by id."""
        ids = [r.id for r in found if r.metadata.kb_id in (kb_id, "")]
        return {chunk.chunk_id: chunk for chunk in self.chunk_repo.find_by_ids(ids, kb_id)}

    @staticmethod
    def _distinct(
        found: list[QueryResult], chunks: dict[str, ContentChunk], top_k: int, min_score: float
    ) -> list[SearchResult]:
        """The best `top_k` results with text, each text once.

        Search answers only with what DynamoDB has: a vector with no chunk (left behind by a delete that failed) has
        nothing to say, and the same text under two chunks (two pages that say the same) is one answer, not two.
        """
        results: list[SearchResult] = []
        said: set[str] = set()
        for result in found:
            chunk = chunks.get(result.id)
            if result.score < min_score or chunk is None:
                continue
            text = " ".join(chunk.content.split())
            if not text or text in said:
                continue
            said.add(text)
            results.append(SearchResult(
                chunk_id=chunk.chunk_id,
                content=chunk.content,
                source_url=chunk.source_url,
                page_title=chunk.page_title or "",
                score=result.score,
                level=chunk.level,
                word_count=chunk.word_count,
                section_heading=chunk.section_heading,
            ))
            if len(results) == top_k:
                break
        return results

    def search_sync(
        self,
        query: str,
        kb_id: str,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> SearchResponse:
        """
        Synchronous version of search for non-async contexts.
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(
            self.search(query, kb_id, top_k, min_score)
        )


# Singleton instance
_search_service: Optional[SemanticSearch] = None


def get_search_service() -> SemanticSearch:
    """Get or create the search service singleton."""
    global _search_service
    if _search_service is None:
        _search_service = SemanticSearch()
    return _search_service
