"""
Pinecone vector database client.

Handles vector storage and retrieval operations for knowledge base content.
Uses namespace isolation per knowledge base.
"""

import logging
from typing import Optional, Any
from dataclasses import dataclass, field

from pinecone import Pinecone

from src.config import settings

log = logging.getLogger(__name__)


@dataclass
class VectorMetadata:
    """Metadata stored with each vector in Pinecone."""
    kb_id: str
    chunk_id: str
    source_url: str
    page_title: str = ""
    chunk_index: int = 0
    level: int = 0  # 0=document, 1=section, 2=paragraph
    word_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kb_id": self.kb_id,
            "chunk_id": self.chunk_id,
            "source_url": self.source_url,
            "page_title": self.page_title,
            "chunk_index": self.chunk_index,
            "level": self.level,
            "word_count": self.word_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VectorMetadata":
        return cls(
            kb_id=data.get("kb_id", ""),
            chunk_id=data.get("chunk_id", ""),
            source_url=data.get("source_url", ""),
            page_title=data.get("page_title", ""),
            chunk_index=data.get("chunk_index", 0),
            level=data.get("level", 0),
            word_count=data.get("word_count", 0),
        )


@dataclass
class VectorRecord:
    """A vector record for upsert operations."""
    id: str  # chunk_id
    values: list[float]  # embedding vector
    metadata: VectorMetadata


@dataclass
class QueryResult:
    """A single query result from Pinecone."""
    id: str  # chunk_id
    score: float
    metadata: VectorMetadata


@dataclass
class QueryResponse:
    """Response from a vector query."""
    results: list[QueryResult] = field(default_factory=list)
    namespace: str = ""


class PineconeClient:
    """
    Client for Pinecone vector database operations.

    Each knowledge base uses a separate namespace within the index
    for isolation and efficient deletion.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        host: Optional[str] = None,
        index_name: Optional[str] = None,
        validate: bool = True,
    ):
        """
        Initialize the Pinecone client.

        Args:
            api_key: Pinecone API key (default: from settings)
            host: Pinecone host URL (default: from settings)
            index_name: Index name (default: from settings)
            validate: Whether to validate config and fail if missing

        Raises:
            ConfigValidationError: If validate=True and required config is missing
        """
        self.api_key = api_key or settings.pinecone_api_key
        self.host = host or settings.pinecone_host
        self.index_name = index_name or settings.pinecone_index
        self._index = None

        # Check if Pinecone is configured
        if not settings.is_pinecone_configured():
            if validate:
                settings.validate_pinecone()  # This will raise ConfigValidationError
            else:
                log.warning(
                    "Pinecone not configured. Set PINECONE_API_KEY, PINECONE_HOST, "
                    "and PINECONE_INDEX environment variables to enable vector search."
                )
                return

        # Initialize Pinecone client
        self._pc = Pinecone(api_key=self.api_key)

        # Connect to the index using the host URL
        self._index = self._pc.Index(host=self.host)
        log.info(f"Connected to Pinecone index at {self.host}")

    def _get_namespace(self, kb_id: str) -> str:
        """Get the namespace for a knowledge base."""
        return f"kb_{kb_id}"

    def upsert(
        self,
        vectors: list[VectorRecord],
        kb_id: str,
        batch_size: int = 100,
    ) -> int:
        """
        Upsert vectors into the index.

        Args:
            vectors: List of VectorRecord objects to upsert
            kb_id: Knowledge base ID for namespace
            batch_size: Number of vectors per batch

        Returns:
            Number of vectors upserted
        """
        if not self._index:
            log.warning("Pinecone index not available, skipping upsert")
            return 0

        namespace = self._get_namespace(kb_id)
        total_upserted = 0

        # Process in batches
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]

            # Convert to Pinecone format
            records = [
                {
                    "id": v.id,
                    "values": v.values,
                    "metadata": v.metadata.to_dict(),
                }
                for v in batch
            ]

            try:
                self._index.upsert(vectors=records, namespace=namespace)
                total_upserted += len(batch)
                log.debug(f"Upserted {len(batch)} vectors to namespace {namespace}")
            except Exception as e:
                log.error(f"Failed to upsert batch: {e}", exc_info=True)

        log.info(f"Upserted {total_upserted} vectors to namespace {namespace}")
        return total_upserted

    def query(
        self,
        vector: list[float],
        kb_id: str,
        top_k: int = 5,
        filter: Optional[dict[str, Any]] = None,
        include_metadata: bool = True,
    ) -> QueryResponse:
        """
        Query vectors by similarity.

        Args:
            vector: Query vector (embedding)
            kb_id: Knowledge base ID for namespace
            top_k: Number of results to return
            filter: Optional metadata filter
            include_metadata: Whether to include metadata in results

        Returns:
            QueryResponse with matching vectors
        """
        if not self._index:
            log.warning("Pinecone index not available, returning empty results")
            return QueryResponse()

        namespace = self._get_namespace(kb_id)

        try:
            response = self._index.query(
                vector=vector,
                namespace=namespace,
                top_k=top_k,
                filter=filter,
                include_metadata=include_metadata,
            )

            results = []
            for match in response.get("matches", []):
                results.append(QueryResult(
                    id=match["id"],
                    score=match["score"],
                    metadata=VectorMetadata.from_dict(match.get("metadata", {})),
                ))

            return QueryResponse(results=results, namespace=namespace)

        except Exception as e:
            log.error(f"Failed to query vectors: {e}", exc_info=True)
            return QueryResponse()

    def query_multiple_kbs(
        self,
        vector: list[float],
        kb_ids: list[str],
        top_k: int = 5,
    ) -> list[QueryResult]:
        """
        Query vectors across multiple knowledge bases.

        Args:
            vector: Query vector (embedding)
            kb_ids: List of knowledge base IDs
            top_k: Number of results per KB

        Returns:
            Combined list of results sorted by score
        """
        all_results: list[QueryResult] = []

        for kb_id in kb_ids:
            response = self.query(vector, kb_id, top_k=top_k)
            all_results.extend(response.results)

        # Sort by score (descending) and return top_k
        all_results.sort(key=lambda r: r.score, reverse=True)
        return all_results[:top_k]

    def delete_by_ids(self, ids: list[str], kb_id: str) -> bool:
        """
        Delete vectors by ID.

        Args:
            ids: List of vector IDs to delete
            kb_id: Knowledge base ID for namespace

        Returns:
            True if successful
        """
        if not self._index:
            return False

        namespace = self._get_namespace(kb_id)

        try:
            self._index.delete(ids=ids, namespace=namespace)
            log.info(f"Deleted {len(ids)} vectors from namespace {namespace}")
            return True
        except Exception as e:
            log.error(f"Failed to delete vectors: {e}", exc_info=True)
            return False

    def delete_namespace(self, kb_id: str) -> bool:
        """
        Delete all vectors in a namespace (entire knowledge base).

        Args:
            kb_id: Knowledge base ID

        Returns:
            True if successful
        """
        if not self._index:
            return False

        namespace = self._get_namespace(kb_id)

        try:
            self._index.delete(delete_all=True, namespace=namespace)
            log.info(f"Deleted all vectors from namespace {namespace}")
            return True
        except Exception as e:
            log.error(f"Failed to delete namespace: {e}", exc_info=True)
            return False

    def get_stats(self, kb_id: Optional[str] = None) -> dict[str, Any]:
        """
        Get index statistics.

        Args:
            kb_id: Optional KB ID to get stats for specific namespace

        Returns:
            Index statistics dict
        """
        if not self._index:
            return {}

        try:
            stats = self._index.describe_index_stats()

            if kb_id:
                namespace = self._get_namespace(kb_id)
                ns_stats = stats.get("namespaces", {}).get(namespace, {})
                return {
                    "namespace": namespace,
                    "vector_count": ns_stats.get("vector_count", 0),
                }

            return {
                "total_vector_count": stats.get("total_vector_count", 0),
                "dimension": stats.get("dimension", 0),
                "namespaces": stats.get("namespaces", {}),
            }
        except Exception as e:
            log.error(f"Failed to get index stats: {e}", exc_info=True)
            return {}


# Singleton instance
_pinecone_client: Optional[PineconeClient] = None


def get_pinecone_client(validate: bool = True) -> PineconeClient:
    """
    Get or create the Pinecone client singleton.

    Args:
        validate: Whether to validate config and fail if missing.
                  Set to False for optional features that should
                  gracefully degrade if Pinecone is not configured.

    Returns:
        PineconeClient instance

    Raises:
        ConfigValidationError: If validate=True and config is missing
    """
    global _pinecone_client
    if _pinecone_client is None:
        _pinecone_client = PineconeClient(validate=validate)
    return _pinecone_client
