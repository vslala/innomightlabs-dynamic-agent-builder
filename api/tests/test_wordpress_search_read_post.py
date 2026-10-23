"""Reading a WordPress post's full content through the REST API, as Markdown."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable

import httpx
import pytest
from pydantic import ValidationError

from src.common import outbound
from src.skills.registry import SkillRegistry
from src.skills.wordpress_search import actions

SITE = "https://example.com"
ENDPOINT = f"{SITE}/wp-json/wp/v2/posts/42"
BODY = """<h2>Research findings</h2>
<p>Some <strong>important</strong> findings, <a href="/more">explained</a>.</p>
<header class="wp-block-group"><p>A block styled as a header is still the post.</p></header>
<ul><li>First finding</li><li>Second finding</li></ul>
<script>SCRIPT_SENTINEL</script>"""
POST = {
    "id": 42,
    "link": f"{SITE}/2026/10/article/",
    "title": {"rendered": "Article &#8217;s research"},
    "date": "2026-10-20T09:00:00",
    "content": {"rendered": BODY, "protected": False},
}
CONFIG = {
    "site_url": "example.com/",
    "username": "reader-user",
    "app_password": "test-application-password",
    "cf_bypass_token": "test-bypass-secret",
}


@pytest.fixture
def mock_http(monkeypatch):
    def install(handler: Callable[[httpx.Request], httpx.Response]) -> list[httpx.Request]:
        requests: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return handler(request)

        monkeypatch.setattr(
            outbound, "async_client", lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(record), **kwargs)
        )
        return requests

    return install


def read(arguments: dict, config: dict | None = None) -> dict:
    return asyncio.run(actions.read_post(arguments, config or CONFIG, {}))


def test_returns_the_whole_post_body_as_markdown(mock_http):
    requests = mock_http(lambda request: httpx.Response(200, json=POST))
    result = read({"id": 42})

    assert result["id"] == 42
    assert result["url"] == f"{SITE}/2026/10/article/"
    assert result["title"] == "Article ’s research"
    assert result["date"] == "2026-10-20T09:00:00"
    markdown = result["markdown"]
    assert markdown.startswith("## Research findings")
    for text in ("**important**", "explained", "A block styled as a header is still the post.", "- First finding"):
        assert text in markdown
    assert "SCRIPT_SENTINEL" not in markdown and "<" not in markdown
    assert result["word_count"] == len(markdown.split())
    assert [str(request.url).split("?")[0] for request in requests] == [ENDPOINT]
    assert requests[0].url.params["_fields"] == "id,link,title,date,content"


def test_authenticates_like_search(mock_http):
    requests = mock_http(lambda request: httpx.Response(200, json=POST))
    read({"id": 42})
    token = base64.b64encode(b"reader-user:test-application-password").decode()
    assert requests[0].headers["Authorization"] == f"Basic {token}"
    assert requests[0].headers["X-Innomightlabs-Skill"] == "test-bypass-secret"


def test_accepts_an_id_given_as_a_string(mock_http):
    requests = mock_http(lambda request: httpx.Response(200, json=POST))
    read({"id": "42"})
    assert str(requests[0].url).startswith(ENDPOINT)


@pytest.mark.parametrize("arguments", [{}, {"id": 0}, {"id": -1}, {"id": "abc"}, {"id": None}])
def test_rejects_a_missing_or_invalid_id(mock_http, arguments):
    requests = mock_http(lambda request: httpx.Response(200, json=POST))
    with pytest.raises(ValidationError):
        read(arguments)
    assert requests == []


def test_site_url_is_required(mock_http):
    with pytest.raises(ValueError, match="'site_url' is required"):
        read({"id": 42}, {"site_url": "  "})


def test_an_api_error_is_reported_with_its_status(mock_http):
    mock_http(lambda request: httpx.Response(404, json={"code": "rest_post_invalid_id"}))
    with pytest.raises(RuntimeError, match=r"WordPress API error \(404\).*rest_post_invalid_id"):
        read({"id": 42})


def test_a_post_without_content_fails(mock_http):
    protected = {**POST, "content": {"rendered": "", "protected": True}}
    mock_http(lambda request: httpx.Response(200, json=protected))
    with pytest.raises(RuntimeError, match="post 42 has no readable content"):
        read({"id": 42})


def test_manifest_registers_read_post(mock_http):
    registry = SkillRegistry()
    loaded = registry.get("wordpress_search")
    assert loaded is not None
    action = loaded.manifest.find_action("read_post")
    assert action is not None and action.handler == "actions:read_post"
    assert action.input_schema["required"] == ["id"]
    assert loaded.manifest.find_action("read_page") is None
    mock_http(lambda request: httpx.Response(200, json=POST))
    result = asyncio.run(registry.execute_action("wordpress_search", "read_post", {"id": 42}, CONFIG, {}))
    assert result["id"] == 42
