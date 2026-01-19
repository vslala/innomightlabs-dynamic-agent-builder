"""
Bedrock Titan embeddings service.

Uses Amazon Bedrock's Titan Text Embeddings V2 model to generate
vector embeddings for text content.
"""

import boto3
import json
import logging
from typing import Optional
from dataclasses import dataclass

from src.config import settings

log = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Result of an embedding operation."""
    embedding: list[float]
    input_text_token_count: int


class BedrockEmbeddings:
    """
    Service for generating text embeddings using Amazon Bedrock Titan.

    Uses the amazon.titan-embed-text-v2:0 model which produces
    1024-dimensional embeddings optimized for semantic search.
    """

    def __init__(
        self,
        model_id: Optional[str] = None,
        region: Optional[str] = None,
        dimension: Optional[int] = None,
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
        import asyncio
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
        import asyncio

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


# Singleton instance
_embeddings_service: Optional[BedrockEmbeddings] = None


def get_embeddings_service() -> BedrockEmbeddings:
    """Get or create the embeddings service singleton."""
    global _embeddings_service
    if _embeddings_service is None:
        _embeddings_service = BedrockEmbeddings()
    return _embeddings_service
