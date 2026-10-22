"""Bounded retries for a sleeping Ollama embedding service."""

import asyncio
import json
from unittest.mock import AsyncMock, call

import httpx
import pytest

from src.vectorstore.embeddings import OllamaEmbeddings


@pytest.fixture
def retry_sleep(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    sleep = AsyncMock()
    monkeypatch.setattr("src.vectorstore.embeddings.asyncio.sleep", sleep)
    return sleep


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [502, 503, 504, httpx.ConnectError])
@pytest.mark.parametrize("recover", [True, False])
async def test_ollama_cold_start_retries_are_bounded(
    failure: int | type[httpx.ConnectError],
    recover: bool,
    retry_sleep: AsyncMock,
) -> None:
    requests: list[httpx.Request] = []
    connection_error = httpx.ConnectError("Connection refused")

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if recover and len(requests) == 4:
            return httpx.Response(
                200,
                json={"embeddings": [[1.0, 0.0], [0.0, 1.0]]},
            )
        if failure is httpx.ConnectError:
            raise connection_error
        assert isinstance(failure, int)
        return httpx.Response(failure)

    provider = OllamaEmbeddings(
        base_url="http://ollama.test",
        model="test-embedding-model",
        dimension=2,
        transport=httpx.MockTransport(handle_request),
    )

    if recover:
        results = await provider.embed_texts_async(["first", "second"])
        assert [result.embedding for result in results] == [[1.0, 0.0], [0.0, 1.0]]
    elif failure is httpx.ConnectError:
        with pytest.raises(httpx.ConnectError) as caught:
            await provider.embed_texts_async(["first", "second"])
        assert caught.value is connection_error
    else:
        with pytest.raises(httpx.HTTPStatusError) as caught_status:
            await provider.embed_texts_async(["first", "second"])
        assert caught_status.value.response.status_code == failure

    assert len(requests) == 4
    assert retry_sleep.await_args_list == [call(1), call(2), call(4)]
    for request in requests:
        assert request.method == "POST"
        assert request.url.path == "/api/embed"
        assert json.loads(request.content) == {
            "model": "test-embedding-model",
            "input": ["first", "second"],
            "dimensions": 2,
            "truncate": True,
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 429, 500])
async def test_ollama_does_not_retry_other_http_errors(
    status: int, retry_sleep: AsyncMock,
) -> None:
    requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status)

    provider = OllamaEmbeddings(transport=httpx.MockTransport(handle_request))
    with pytest.raises(httpx.HTTPStatusError) as caught:
        await provider.embed_text_async("hello")

    assert caught.value.response.status_code == status
    assert len(requests) == 1
    retry_sleep.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_type",
    [httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ReadError, asyncio.CancelledError],
)
async def test_ollama_does_not_retry_timeouts_read_errors_or_cancellation(
    error_type: type[BaseException], retry_sleep: AsyncMock,
) -> None:
    requests: list[httpx.Request] = []
    error = error_type("request interrupted")

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise error

    provider = OllamaEmbeddings(transport=httpx.MockTransport(handle_request))
    with pytest.raises(error_type) as caught:
        await provider.embed_text_async("hello")

    assert caught.value is error
    assert len(requests) == 1
    retry_sleep.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [b"not json", b'{}', b'{"embeddings": []}', b'{"embeddings": [[1.0]]}'],
)
async def test_ollama_does_not_retry_invalid_responses(
    content: bytes, retry_sleep: AsyncMock,
) -> None:
    requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=content)

    provider = OllamaEmbeddings(
        dimension=2, transport=httpx.MockTransport(handle_request),
    )
    with pytest.raises(ValueError):
        await provider.embed_text_async("hello")

    assert len(requests) == 1
    retry_sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_ollama_validation_does_not_make_requests(retry_sleep: AsyncMock) -> None:
    requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    provider = OllamaEmbeddings(transport=httpx.MockTransport(handle_request))
    with pytest.raises(ValueError, match="always normalized"):
        await provider.embed_text_async("hello", normalize=False)
    assert await provider.embed_texts_async([]) == []

    assert requests == []
    retry_sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_ollama_cancellation_during_backoff_stops_retries(
    retry_sleep: AsyncMock,
) -> None:
    requests: list[httpx.Request] = []
    retry_sleep.side_effect = asyncio.CancelledError

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503)

    provider = OllamaEmbeddings(transport=httpx.MockTransport(handle_request))
    with pytest.raises(asyncio.CancelledError):
        await provider.embed_text_async("hello")

    assert len(requests) == 1
    retry_sleep.assert_awaited_once_with(1)
