import json

import httpx
import pytest

from src.tools.http_executor import HttpExecutor, HttpExecutorError


@pytest.mark.asyncio
async def test_http_executor_blocks_localhost(monkeypatch):
    import src.config as config

    monkeypatch.setattr(config.settings, "http_executor_allow_local", False, raising=False)
    ex = HttpExecutor(client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))))
    with pytest.raises(HttpExecutorError):
        await ex.request("GET", "http://localhost:1234/")


@pytest.mark.asyncio
async def test_http_executor_blocks_private_ip_literal(monkeypatch):
    import src.config as config

    monkeypatch.setattr(config.settings, "http_executor_allow_local", False, raising=False)
    ex = HttpExecutor(client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))))
    with pytest.raises(HttpExecutorError):
        await ex.request("GET", "http://10.0.0.1/")


@pytest.mark.asyncio
async def test_http_executor_allows_localhost_in_dev(monkeypatch):
    import src.config as config

    monkeypatch.setattr(config.settings, "http_executor_allow_local", True, raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        ex = HttpExecutor(client=client)
        res = await ex.request("GET", "http://localhost:1234/")
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_http_executor_merges_query_params_and_returns_body():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["a"] == "1"
        assert request.url.params["b"] == "2"
        return httpx.Response(200, json={"ok": True, "url": str(request.url)})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        ex = HttpExecutor(client=client)
        res = await ex.request("GET", "https://example.com/path?a=1", query={"b": 2})
        payload = json.loads(res.body_text)
        assert payload["ok"] is True
        assert res.status_code == 200
