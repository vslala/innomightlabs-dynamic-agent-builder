"""Vector store module for embeddings and semantic search."""

from src.vectorstore.embeddings import (
    BedrockEmbeddings,
    EmbeddingResult,
    get_embeddings_service,
)

from src.vectorstore.pinecone_client import (
    PineconeClient,
    VectorMetadata,
    VectorRecord,
    QueryResult,
    QueryResponse,
    get_pinecone_client,
)

from src.vectorstore.search import (
    SemanticSearch,
    SearchResult,
    SearchResponse,
    get_search_service,
)

__all__ = [
    # Embeddings
    "BedrockEmbeddings",
    "EmbeddingResult",
    "get_embeddings_service",
    # Pinecone
    "PineconeClient",
    "VectorMetadata",
    "VectorRecord",
    "QueryResult",
    "QueryResponse",
    "get_pinecone_client",
    # Search
    "SemanticSearch",
    "SearchResult",
    "SearchResponse",
    "get_search_service",
]
