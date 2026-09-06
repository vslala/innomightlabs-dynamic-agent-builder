from __future__ import annotations

import json

import httpx
import pytest

from src.vectorstore.embeddings import (
    BedrockEmbeddings,
    OllamaEmbeddings,
    create_embeddings_service,
)


@pytest.mark.asyncio
async def test_ollama_provider_batches_texts_and_preserves_order() -> None:
    requests: list[dict] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "embeddings": [
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                ],
                "prompt_eval_count": 8,
            },
        )

    provider = OllamaEmbeddings(
        base_url="http://ollama.test",
        model="test-embedding-model",
        dimension=3,
        transport=httpx.MockTransport(handle_request),
    )

    results = await provider.embed_texts_async(["first", "second"])

    assert [result.embedding for result in results] == [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
    ]
    assert requests == [
        {
            "model": "test-embedding-model",
            "input": ["first", "second"],
            "dimensions": 3,
            "truncate": True,
        }
    ]


@pytest.mark.asyncio
async def test_ollama_provider_reports_single_input_token_count() -> None:
    def handle_request(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "embeddings": [[1.0, 0.0, 0.0]],
                "prompt_eval_count": 4,
            },
        )

    provider = OllamaEmbeddings(
        base_url="http://ollama.test",
        dimension=3,
        transport=httpx.MockTransport(handle_request),
    )

    result = await provider.embed_text_async("hello")

    assert result.embedding == [1.0, 0.0, 0.0]
    assert result.input_text_token_count == 4


@pytest.mark.asyncio
async def test_ollama_provider_rejects_dimension_mismatch() -> None:
    def handle_request(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0]]})

    provider = OllamaEmbeddings(
        base_url="http://ollama.test",
        dimension=3,
        transport=httpx.MockTransport(handle_request),
    )

    with pytest.raises(ValueError, match="expected 3, received 2"):
        await provider.embed_text_async("hello")


def test_embedding_provider_factory_selects_bedrock(mock_aws_context) -> None:
    provider = create_embeddings_service("bedrock")

    assert isinstance(provider, BedrockEmbeddings)


def test_embedding_provider_factory_selects_ollama() -> None:
    provider = create_embeddings_service("ollama")

    assert isinstance(provider, OllamaEmbeddings)


def test_embedding_provider_factory_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="Unsupported embedding backend"):
        create_embeddings_service("unknown")
