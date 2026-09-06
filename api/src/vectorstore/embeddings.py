"""Embedding providers used by knowledge indexing and semantic search."""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Protocol

import boto3
import httpx

from src.config import settings

log = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Result of an embedding operation."""
    embedding: list[float]
    input_text_token_count: int


class EmbeddingProvider(Protocol):
    """Contract shared by remote and local embedding providers."""

    dimension: int

    async def embed_text_async(
        self,
        text: str,
        normalize: bool = True,
    ) -> EmbeddingResult:
        """Generate one embedding."""
        ...

    async def embed_texts_async(
        self,
        texts: list[str],
        normalize: bool = True,
        max_concurrent: int = 5,
    ) -> list[EmbeddingResult]:
        """Generate embeddings in input order."""
        ...


class BedrockEmbeddings:
    """
    Service for generating text embeddings using Amazon Bedrock Titan.

    Uses the amazon.titan-embed-text-v2:0 model which produces
    1024-dimensional embeddings optimized for semantic search.
    """

    def __init__(
        self,
        model_id: str | None = None,
        region: str | None = None,
        dimension: int | None = None,
    ):
        """
        Initialize the Bedrock embeddings service.

        Args:
            model_id: Bedrock model ID (default: from settings)
            region: AWS region (default: from settings)
            dimension: Embedding dimension (default: from settings)
        """
        self.model_id = model_id or settings.bedrock_embedding_model
        self.region = region or settings.aws_region
        self.dimension = dimension or settings.bedrock_embedding_dimension

        # Initialize Bedrock runtime client
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=self.region,
        )

    def embed_text(self, text: str, normalize: bool = True) -> EmbeddingResult:
        """
        Generate embedding for a single text.

        Args:
            text: The text to embed
            normalize: Whether to normalize the embedding (default: True)

        Returns:
            EmbeddingResult with embedding vector and token count
        """
        # Prepare request body for Titan Embeddings V2
        body = {
            "inputText": text,
            "dimensions": self.dimension,
            "normalize": normalize,
        }

        try:
            response = self._client.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )

            response_body = json.loads(response["body"].read())

            return EmbeddingResult(
                embedding=response_body["embedding"],
                input_text_token_count=response_body.get("inputTextTokenCount", 0),
            )

        except Exception as e:
            log.error(f"Failed to generate embedding: {e}", exc_info=True)
            raise

    def embed_texts(
        self,
        texts: list[str],
        normalize: bool = True,
        batch_size: int = 10,
    ) -> list[EmbeddingResult]:
        """
        Generate embeddings for multiple texts.

        Note: Titan Embeddings V2 doesn't support batch requests,
        so we process texts sequentially. For large batches, consider
        using async processing.

        Args:
            texts: List of texts to embed
            normalize: Whether to normalize embeddings
            batch_size: Not used (for API compatibility)

        Returns:
            List of EmbeddingResult objects
        """
        results = []

        for text in texts:
            try:
                result = self.embed_text(text, normalize=normalize)
                results.append(result)
            except Exception as e:
                log.error(f"Failed to embed text: {e}")
                # Add empty embedding for failed texts to maintain index alignment
                results.append(EmbeddingResult(
                    embedding=[0.0] * self.dimension,
                    input_text_token_count=0,
                ))

        return results

    async def embed_text_async(self, text: str, normalize: bool = True) -> EmbeddingResult:
        """
        Async wrapper for embed_text.

        Note: boto3 doesn't have native async support, so this runs
        the sync version. For true async, consider using aioboto3.
        """
        return await asyncio.to_thread(self.embed_text, text, normalize)

    async def embed_texts_async(
        self,
        texts: list[str],
        normalize: bool = True,
        max_concurrent: int = 5,
    ) -> list[EmbeddingResult]:
        """
        Generate embeddings for multiple texts asynchronously.

        Args:
            texts: List of texts to embed
            normalize: Whether to normalize embeddings
            max_concurrent: Maximum concurrent embedding requests

        Returns:
            List of EmbeddingResult objects
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def embed_with_semaphore(text: str) -> EmbeddingResult:
            async with semaphore:
                try:
                    return await self.embed_text_async(text, normalize)
                except Exception as e:
                    log.error(f"Failed to embed text: {e}")
                    return EmbeddingResult(
                        embedding=[0.0] * self.dimension,
                        input_text_token_count=0,
                    )

        tasks = [embed_with_semaphore(text) for text in texts]
        results = await asyncio.gather(*tasks)

        return list(results)


class OllamaEmbeddings:
    """Generate embeddings through Ollama's local HTTP API."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
        timeout_seconds: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_embedding_model
        self.dimension = dimension or settings.embedding_dimension
        self.timeout_seconds = timeout_seconds or settings.ollama_timeout_seconds
        self.transport = transport

    async def embed_text_async(
        self,
        text: str,
        normalize: bool = True,
    ) -> EmbeddingResult:
        results = await self.embed_texts_async([text], normalize=normalize)
        return results[0]

    async def embed_texts_async(
        self,
        texts: list[str],
        normalize: bool = True,
        max_concurrent: int = 5,
    ) -> list[EmbeddingResult]:
        del max_concurrent  # Ollama performs batching inside a single request.
        if not texts:
            return []
        if not normalize:
            raise ValueError("Ollama embeddings are always normalized")

        request_body = {
            "model": self.model,
            "input": texts,
            "dimensions": self.dimension,
            "truncate": True,
        }
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            response = await client.post("/api/embed", json=request_body)
            response.raise_for_status()

        response_body = response.json()
        embeddings = response_body.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise ValueError(
                "Ollama returned an unexpected number of embedding vectors"
            )

        results: list[EmbeddingResult] = []
        for embedding in embeddings:
            if not isinstance(embedding, list) or len(embedding) != self.dimension:
                actual_dimension = len(embedding) if isinstance(embedding, list) else 0
                raise ValueError(
                    "Ollama embedding dimension mismatch: "
                    f"expected {self.dimension}, received {actual_dimension}"
                )
            results.append(
                EmbeddingResult(
                    embedding=embedding,
                    input_text_token_count=0,
                )
            )

        if len(results) == 1:
            results[0].input_text_token_count = int(
                response_body.get("prompt_eval_count", 0)
            )
        return results


# Singleton instance
_embeddings_service: EmbeddingProvider | None = None


def create_embeddings_service(backend: str | None = None) -> EmbeddingProvider:
    """Create the configured provider without using the process singleton."""
    selected_backend = (backend or settings.embedding_backend).strip().lower()
    if selected_backend == "bedrock":
        return BedrockEmbeddings(dimension=settings.embedding_dimension)
    if selected_backend == "ollama":
        return OllamaEmbeddings()
    raise ValueError(
        f"Unsupported embedding backend {selected_backend!r}; expected 'bedrock' or 'ollama'"
    )


def get_embeddings_service() -> EmbeddingProvider:
    """Get or create the embeddings service singleton."""
    global _embeddings_service
    if _embeddings_service is None:
        _embeddings_service = create_embeddings_service()
    return _embeddings_service
