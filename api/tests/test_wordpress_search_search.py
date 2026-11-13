"""Finding WordPress posts by a query, or listing them by filters alone, through the REST API."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx
import pytest
from pydantic import ValidationError

from src.common import outbound
from src.skills.registry import SkillRegistry
from src.skills.wordpress_search import actions

SITE = "https://example.com"
CONFIG = {"site_url": SITE, "cf_bypass_token": "test-bypass-secret"}
POSTS = [
    {
        "id": 7,
        "date": "2026-11-12T08:00:00",
        "title": {"rendered": "Newest &#8217;s post"},
        "link": f"{SITE}/newest/",
        "author": 1,
        "categories": [3],
    }
]


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


def posts_only(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=POSTS)


def search(arguments: dict) -> str:
    return asyncio.run(actions.search(arguments, CONFIG, {}))


@pytest.mark.parametrize("arguments", [{}, {"query": ""}, {"query": "  ", "orderby": ""}, {"query": None}])
def test_without_a_query_the_newest_posts_are_listed(mock_http, arguments):
    requests = mock_http(posts_only)

    result = search({**arguments, "per_page": 1})

    params = requests[0].url.params
    assert "search" not in params
    assert (params["orderby"], params["order"], params["per_page"], params["status"]) == ("date", "desc", "1", "publish")
    assert "[7] Newest ’s post" in result and "read_post" in result


def test_relevance_without_a_query_falls_back_to_date_as_wordpress_refuses_it(mock_http):
    requests = mock_http(posts_only)

    search({"orderby": "relevance"})

    assert requests[0].url.params["orderby"] == "date"


def test_a_query_is_searched_by_relevance(mock_http):
    requests = mock_http(posts_only)

    search({"query": " Instagram tips "})

    assert (requests[0].url.params["search"], requests[0].url.params["orderby"]) == ("Instagram tips", "relevance")


def test_filters_alone_select_the_posts(mock_http):
    def site(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/categories"):
            return httpx.Response(200, json=[{"id": 3}] if request.url.params.get("slug") == "travel" else [])
        return httpx.Response(200, json=POSTS)

    requests = mock_http(site)

    search({"author": "1", "category": "travel, 3", "after": "2026-11-01", "per_page": 50, "page": 0})

    params = requests[-1].url.params
    assert (params["author"], params["categories"], params["after"]) == ("1", "3", "2026-11-01")
    assert (params["per_page"], params["page"]) == ("20", "1")


def test_names_are_looked_up_by_slug_then_by_search(mock_http):
    def site(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/users"):
            return httpx.Response(200, json=[{"id": 9}] if "search" in request.url.params else [])
        return httpx.Response(200, json=POSTS)

    requests = mock_http(site)

    search({"author": "Varun"})

    assert [list(request.url.params)[0] for request in requests[:2]] == ["slug", "search"]
    assert requests[-1].url.params["author"] == "9"


def test_an_author_that_matches_no_one_is_an_error(mock_http):
    mock_http(lambda request: httpx.Response(200, json=[]))

    with pytest.raises(ValueError, match="Author filter did not match any user: 'nobody'"):
        search({"author": "nobody"})


def test_the_site_firewall_token_is_sent(mock_http):
    requests = mock_http(posts_only)

    search({})

    assert requests[0].headers["X-Innomightlabs-Skill"] == "test-bypass-secret"


def test_an_unknown_choice_is_refused_before_any_request(mock_http):
    requests = mock_http(posts_only)

    with pytest.raises(ValidationError):
        search({"order": "newest"})
    assert requests == []


def test_no_posts_is_said_plainly(mock_http):
    mock_http(lambda request: httpx.Response(200, json=[]))

    assert search({}) == "No WordPress posts matched."


def test_the_manifest_requires_nothing_for_search():
    action = SkillRegistry().get("wordpress_search").manifest.find_action("search")

    assert "required" not in action.input_schema
