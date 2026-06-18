from __future__ import annotations

import asyncio

import httpx
import pytest

from src.skills.registry import SkillRegistry
from src.skills.rest_template.actions import get, post
from src.skills.rest_template.helper import expand_env_placeholders, redact_headers, redact_url
from src.skills.rest_template.models import MAX_TIMEOUT_SECONDS, RestRequest


class FakeAsyncClient:
    def __init__(self, response: httpx.Response | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if self.error:
            raise self.error
        return self.response


def _response(
    status_code: int = 200,
    *,
    text: str = "",
    json_data=None,
    headers: dict[str, str] | None = None,
    url: str = "https://api.example.com/items?token=secret",
) -> httpx.Response:
    request = httpx.Request("GET", url)
    if json_data is not None:
        return httpx.Response(status_code, json=json_data, headers=headers, request=request)
    return httpx.Response(status_code, text=text, headers=headers, request=request)


def test_rest_template_get_sends_url_headers_and_query(monkeypatch):
    fake_client = FakeAsyncClient(_response(json_data={"items": []}))
    monkeypatch.setattr(
        "src.skills.rest_template.actions.httpx.AsyncClient",
        lambda timeout, follow_redirects: fake_client,
    )

    result = asyncio.run(
        get(
            {
                "url": "https://api.example.com/items",
                "headers": {"Accept": "application/json"},
                "query": {"page": 1},
            },
            {},
            {},
        )
    )

    assert result == {"ok": True, "status_code": 200, "body_preview": '{"items":[]}'}
    assert fake_client.calls == [
        {
            "method": "GET",
            "url": "https://api.example.com/items",
            "params": {"page": "1"},
            "headers": {"Accept": "application/json"},
        }
    ]


def test_rest_template_post_sends_json_body(monkeypatch):
    fake_client = FakeAsyncClient(_response(status_code=201, json_data={"created": True}))
    monkeypatch.setattr(
        "src.skills.rest_template.actions.httpx.AsyncClient",
        lambda timeout, follow_redirects: fake_client,
    )

    result = asyncio.run(
        post(
            {
                "url": "https://api.example.com/items",
                "headers": {"Content-Type": "application/json"},
                "json_body": '{"name":"Example"}',
            },
            {},
            {},
        )
    )

    assert result["ok"] is True
    assert result["status_code"] == 201
    assert fake_client.calls[0]["json"] == {"name": "Example"}
    assert "content" not in fake_client.calls[0]


def test_rest_template_post_rejects_json_and_text_body():
    with pytest.raises(ValueError, match="Provide either json_body or text_body"):
        asyncio.run(
            post(
                {
                    "url": "https://api.example.com/items",
                    "json_body": {"name": "Example"},
                    "text_body": "raw",
                },
                {},
                {},
            )
        )


def test_rest_template_url_validation_and_timeout_clamping():
    with pytest.raises(ValueError, match="absolute http or https"):
        RestRequest.model_validate({"url": "/relative"})

    with pytest.raises(ValueError, match="embedded username or password"):
        RestRequest.model_validate({"url": "https://user:pass@example.com"})

    request = RestRequest.model_validate({"url": "https://api.example.com", "timeout_seconds": 999})
    assert request.timeout_seconds == MAX_TIMEOUT_SECONDS


def test_rest_template_full_response_includes_json_and_redacts_headers(monkeypatch):
    fake_client = FakeAsyncClient(
        _response(
            json_data={"items": []},
            headers={
                "content-type": "application/json",
                "set-cookie": "session=secret",
                "x-request-id": "req-1",
            },
        )
    )
    monkeypatch.setattr(
        "src.skills.rest_template.actions.httpx.AsyncClient",
        lambda timeout, follow_redirects: fake_client,
    )

    result = asyncio.run(
        get(
            {
                "url": "https://api.example.com/items",
                "include_full_response": True,
            },
            {},
            {},
        )
    )

    assert result["ok"] is True
    assert result["body_json"] == {"items": []}
    assert result["headers"]["set-cookie"] == "[redacted]"
    assert result["headers"]["x-request-id"] == "req-1"
    assert result["url"] == "https://api.example.com/items"
    assert result["truncated"] is False


def test_rest_template_non_json_full_response_has_preview_without_body_json(monkeypatch):
    fake_client = FakeAsyncClient(_response(text="plain text", headers={"content-type": "text/plain"}))
    monkeypatch.setattr(
        "src.skills.rest_template.actions.httpx.AsyncClient",
        lambda timeout, follow_redirects: fake_client,
    )

    result = asyncio.run(
        get(
            {
                "url": "https://api.example.com/items",
                "include_full_response": True,
            },
            {},
            {},
        )
    )

    assert result["body_preview"] == "plain text"
    assert "body_json" not in result


def test_rest_template_large_response_truncates_only_reporting_flag_in_full_response(monkeypatch):
    fake_client = FakeAsyncClient(_response(text="abcdef"))
    monkeypatch.setattr(
        "src.skills.rest_template.actions.httpx.AsyncClient",
        lambda timeout, follow_redirects: fake_client,
    )

    compact = asyncio.run(get({"url": "https://api.example.com/items", "max_response_chars": 3}, {}, {}))
    assert compact == {"ok": True, "status_code": 200, "body_preview": "abc"}

    fake_client.response = _response(text="abcdef")
    full = asyncio.run(
        get(
            {
                "url": "https://api.example.com/items",
                "max_response_chars": 3,
                "include_full_response": True,
            },
            {},
            {},
        )
    )
    assert full["body_preview"] == "abc"
    assert full["truncated"] is True


def test_rest_template_http_error_returns_branchable_payload(monkeypatch):
    fake_client = FakeAsyncClient(_response(status_code=401, text='{"error":"invalid token"}'))
    monkeypatch.setattr(
        "src.skills.rest_template.actions.httpx.AsyncClient",
        lambda timeout, follow_redirects: fake_client,
    )

    result = asyncio.run(get({"url": "https://api.example.com/items"}, {}, {}))

    assert result == {
        "ok": False,
        "status_code": 401,
        "body_preview": '{"error":"invalid token"}',
    }


def test_rest_template_transport_error_returns_human_readable_payload(monkeypatch):
    request = httpx.Request("GET", "https://api.example.com/items")
    fake_client = FakeAsyncClient(error=httpx.ConnectError("network unreachable", request=request))
    monkeypatch.setattr(
        "src.skills.rest_template.actions.httpx.AsyncClient",
        lambda timeout, follow_redirects: fake_client,
    )

    result = asyncio.run(get({"url": "https://api.example.com/items?token=secret"}, {}, {}))

    assert result["ok"] is False
    assert result["status_code"] is None
    assert result["body_preview"] == ""
    assert "could not connect" in result["error"]
    assert "token=secret" not in result["error"]


def test_rest_template_environment_placeholders_are_resolved(monkeypatch):
    monkeypatch.setenv("api_token", "secret-token")
    fake_client = FakeAsyncClient(_response(json_data={"ok": True}))
    monkeypatch.setattr(
        "src.skills.rest_template.actions.httpx.AsyncClient",
        lambda timeout, follow_redirects: fake_client,
    )

    asyncio.run(
        get(
            {
                "url": "https://api.example.com/items",
                "headers": {"Authorization": "Bearer {{ api_token }}"},
            },
            {},
            {},
        )
    )

    assert fake_client.calls[0]["headers"]["Authorization"] == "Bearer secret-token"


def test_rest_template_missing_environment_placeholder_fails_before_dispatch(monkeypatch):
    monkeypatch.delenv("api_token", raising=False)
    fake_client = FakeAsyncClient(_response(json_data={"ok": True}))
    monkeypatch.setattr(
        "src.skills.rest_template.actions.httpx.AsyncClient",
        lambda timeout, follow_redirects: fake_client,
    )

    with pytest.raises(ValueError, match="api_token"):
        asyncio.run(
            get(
                {
                    "url": "https://api.example.com/items",
                    "headers": {"Authorization": "Bearer {{ api_token }}"},
                },
                {},
                {},
            )
        )
    assert fake_client.calls == []


def test_rest_template_helper_redaction_and_placeholder(monkeypatch):
    monkeypatch.setenv("api_token", "secret-token")
    assert expand_env_placeholders({"header": "Bearer {{ api_token }}"}) == {"header": "Bearer secret-token"}
    assert redact_headers({"Authorization": "Bearer secret", "x-trace": "1"}) == {
        "Authorization": "[redacted]",
        "x-trace": "1",
    }
    assert redact_url("https://api.example.com/items?token=secret") == "https://api.example.com/items"


def test_rest_template_registry_alias_uses_get_handler(monkeypatch):
    fake_client = FakeAsyncClient(_response(text="ok"))
    monkeypatch.setattr(
        "src.skills.rest_template.actions.httpx.AsyncClient",
        lambda timeout, follow_redirects: fake_client,
    )

    registry = SkillRegistry()
    result = asyncio.run(
        registry.execute_action(
            skill_id="rest_template",
            action_name="http_get",
            arguments={"url": "https://api.example.com/items"},
            config={},
            context={},
        )
    )

    assert result == {"ok": True, "status_code": 200, "body_preview": "ok"}
    assert fake_client.calls[0]["method"] == "GET"
