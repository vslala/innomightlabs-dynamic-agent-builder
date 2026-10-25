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
async def test_ollama_provider_sends_many_texts_in_batches_and_keeps_their_order() -> None:
    from src.vectorstore.embeddings import OLLAMA_EMBED_BATCH_SIZE

    batches: list[list[str]] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["input"]
        batches.append(texts)
        return httpx.Response(200, json={"embeddings": [[float(text), 0.0, 0.0] for text in texts]})

    provider = OllamaEmbeddings(
        base_url="http://ollama.test", model="m", dimension=3, transport=httpx.MockTransport(handle_request)
    )
    texts = [str(n) for n in range(OLLAMA_EMBED_BATCH_SIZE * 2 + 3)]

    results = await provider.embed_texts_async(texts)

    assert [len(batch) for batch in batches] == [OLLAMA_EMBED_BATCH_SIZE, OLLAMA_EMBED_BATCH_SIZE, 3]
    assert [result.embedding[0] for result in results] == [float(n) for n in range(len(texts))]


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


def throttled_bedrock(mock_aws_context) -> BedrockEmbeddings:
    from botocore.exceptions import ClientError

    provider = create_embeddings_service("bedrock")
    assert isinstance(provider, BedrockEmbeddings)

    def invoke_model(**_):
        raise ClientError({"Error": {"Code": "ThrottlingException", "Message": "Too many requests"}}, "InvokeModel")

    provider._client.invoke_model = invoke_model  # type: ignore[method-assign]
    return provider


@pytest.mark.asyncio
async def test_bedrock_raises_when_it_cant_embed_a_text_instead_of_returning_a_made_up_vector(mock_aws_context) -> None:
    provider = throttled_bedrock(mock_aws_context)

    with pytest.raises(Exception, match="ThrottlingException"):
        await provider.embed_texts_async(["Seats cost ten pounds."])


def test_bedrock_raises_for_the_sequential_api_too(mock_aws_context) -> None:
    provider = throttled_bedrock(mock_aws_context)

    with pytest.raises(Exception, match="ThrottlingException"):
        provider.embed_texts(["Seats cost ten pounds."])


def test_bedrock_backs_off_and_retries_when_throttled(mock_aws_context) -> None:
    from src.vectorstore.embeddings import BEDROCK_RETRY_ATTEMPTS

    provider = create_embeddings_service("bedrock")
    assert isinstance(provider, BedrockEmbeddings)

    retries = provider._client.meta.config.retries
    assert retries["mode"] == "adaptive" and retries["total_max_attempts"] == BEDROCK_RETRY_ATTEMPTS + 1 > 5
