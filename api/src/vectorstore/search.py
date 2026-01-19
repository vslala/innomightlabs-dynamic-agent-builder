"""
Semantic search service for knowledge bases.

Combines Bedrock embeddings and Pinecone for full semantic search
with content retrieval from DynamoDB.
"""

import logging
from typing import Optional
from dataclasses import dataclass

from src.vectorstore.embeddings import BedrockEmbeddings, get_embeddings_service
from src.vectorstore.pinecone_client import PineconeClient, get_pinecone_client, QueryResult
from src.knowledge.repository import ContentChunkRepository

log = logging.getLogger(__name__)


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
    1. Embed the query using Bedrock
    2. Search Pinecone for similar vectors
    3. Retrieve full content from DynamoDB
    4. Return enriched results
    """

    def __init__(
        self,
        embeddings: Optional[BedrockEmbeddings] = None,
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

        # Step 3: Query Pinecone
        response = self.pinecone.query(
            vector=query_vector,
            kb_id=kb_id,
            top_k=top_k * 2,  # Get more results to filter by score
            filter=pinecone_filter,
        )

        # Step 4: Filter by score and limit
        filtered_results = [
            r for r in response.results
            if r.score >= min_score
        ][:top_k]

        if not filtered_results:
            return SearchResponse(results=[], query=query, kb_id=kb_id)

        # Step 5: Retrieve full content from DynamoDB
        chunk_ids = [r.id for r in filtered_results]
        chunks = self.chunk_repo.find_by_ids(chunk_ids, kb_id)
        chunk_map = {c.chunk_id: c for c in chunks}

        # Step 6: Build enriched results
        results = []
        for r in filtered_results:
            chunk = chunk_map.get(r.id)
            if chunk:
                results.append(SearchResult(
                    chunk_id=r.id,
                    content=chunk.content,
                    source_url=chunk.source_url,
                    page_title=chunk.page_title or "",
                    score=r.score,
                    level=chunk.level,
                    word_count=chunk.word_count,
                ))
            else:
                # Fallback to metadata if chunk not found in DynamoDB
                results.append(SearchResult(
                    chunk_id=r.id,
                    content="",  # Content not available
                    source_url=r.metadata.source_url,
                    page_title=r.metadata.page_title,
                    score=r.score,
                    level=r.metadata.level,
                    word_count=r.metadata.word_count,
                ))

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

        # Query all KBs
        all_vector_results = self.pinecone.query_multiple_kbs(
            vector=query_vector,
            kb_ids=kb_ids,
            top_k=top_k,
        )

        # Filter by score
        filtered_results = [
            r for r in all_vector_results
            if r.score >= min_score
        ][:top_k]

        if not filtered_results:
            return []

        # Group by KB for efficient content retrieval
        kb_chunks: dict[str, list[str]] = {}
        for r in filtered_results:
            kb_id = r.metadata.kb_id
            if kb_id not in kb_chunks:
                kb_chunks[kb_id] = []
            kb_chunks[kb_id].append(r.id)

        # Retrieve content from each KB
        all_chunks = {}
        for kb_id, chunk_ids in kb_chunks.items():
            chunks = self.chunk_repo.find_by_ids(chunk_ids, kb_id)
            for c in chunks:
                all_chunks[c.chunk_id] = c

        # Build enriched results
        results = []
        for r in filtered_results:
            chunk = all_chunks.get(r.id)
            if chunk:
                results.append(SearchResult(
                    chunk_id=r.id,
                    content=chunk.content,
                    source_url=chunk.source_url,
                    page_title=chunk.page_title or "",
                    score=r.score,
                    level=chunk.level,
                    word_count=chunk.word_count,
                ))

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
