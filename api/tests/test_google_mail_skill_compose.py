from __future__ import annotations

import asyncio
import base64
import json
from email import policy
from email.parser import BytesParser
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from src.skills.google_mail import actions
from src.skills.registry import SkillRegistry


COMPOSE = {
    "to": ['"Zoë, Team" <zoe@example.com>'],
    "cc": ["Renée <renee@example.com>"],
    "bcc": ["private@example.com"],
    "subject": "Résumé — こんにちは",
    "body": "Hello Zoë\nこんにちは",
    "html_body": "<p>Hello Zoë — こんにちは</p>",
}


@pytest.fixture
def gmail(monkeypatch):
    calls: list[httpx.Request] = []
    responses: list[httpx.Response | Exception] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        response = responses.pop(0) if responses else httpx.Response(200, json={"id": "result-1"})
        if isinstance(response, Exception):
            raise response
        return response

    client_class = httpx.AsyncClient
    token = AsyncMock(return_value="access-token")
    monkeypatch.setattr(actions, "_get_access_token", token)
    monkeypatch.setattr(
        actions.httpx, "AsyncClient",
        lambda timeout: client_class(timeout=timeout, transport=httpx.MockTransport(handle)),
    )
    return calls, responses, token


@pytest.mark.parametrize(
    ("action", "extra", "method", "path"),
    [
        ("create_draft", {}, "POST", "/drafts"),
        ("update_draft", {"draft_id": "draft-1"}, "PUT", "/drafts/draft-1"),
        ("send", {"confirmed": True}, "POST", "/messages/send"),
    ],
)
def test_compose_mime_and_payload(gmail, action, extra, method, path):
    calls, _, token = gmail
    result = asyncio.run(getattr(actions, action)({**COMPOSE, **extra}, {}, {"account_id": "account-1"}))
    assert "result-1" in result
    assert len(calls) == 1
    request = calls[0]
    assert request.method == method
    assert str(request.url).endswith(path)
    assert request.headers["authorization"] == "Bearer access-token"
    token.assert_awaited_once_with({"account_id": "account-1"})
    payload = json.loads(request.content)
    if action != "send":
        assert set(payload) == {"message"}
        payload = payload["message"]
    assert set(payload) == {"raw"}
    message = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(payload["raw"]))
    assert str(message["Subject"]) == COMPOSE["subject"]
    assert message["To"].addresses[0].display_name == "Zoë, Team"
    assert message["To"].addresses[0].addr_spec == "zoe@example.com"
    assert message["Cc"].addresses[0].display_name == "Renée"
    assert message["Bcc"].addresses[0].addr_spec == "private@example.com"
    assert message["From"] is None
    assert message.get_content_type() == "multipart/alternative"
    assert message.get_body(preferencelist=("plain",)).get_content().replace("\r\n", "\n").rstrip("\n") == COMPOSE["body"]
    assert message.get_body(preferencelist=("html",)).get_content().strip() == COMPOSE["html_body"]


def test_plain_text_bcc_only_draft(gmail):
    calls, _, _ = gmail
    asyncio.run(actions.create_draft({"bcc": ["private@example.com"], "subject": "", "body": ""}, {}, {}))
    payload = json.loads(calls[0].content)
    message = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(payload["message"]["raw"]))
    assert message.get_content_type() == "text/plain"
    assert message["To"] is None
    assert message["Bcc"] is not None


def test_send_draft_uses_draft_id_only(gmail):
    calls, _, _ = gmail
    result = asyncio.run(actions.send_draft({"draft_id": "r-draft_1", "confirmed": True}, {}, {}))
    assert "succeeded" in result
    assert str(calls[0].url).endswith("/drafts/send")
    assert json.loads(calls[0].content) == {"id": "r-draft_1"}


@pytest.mark.parametrize("field", ["to", "cc", "bcc"])
@pytest.mark.parametrize("recipient", [
    "", "not-an-email", "a@example.com\r\nBcc: injected@example.com",
    "a@example.com\x00", "a@example.com, b@example.com", "a@", "a@@example.com",
    "a@example..com", "a@-example.com", "Group: a@example.com;", "é@example.com",
    "a@example.com garbage", "<a@example.com", "a example@example.com",
])
def test_invalid_recipients_rejected_before_credentials(gmail, field, recipient):
    calls, _, token = gmail
    with pytest.raises(ValueError, match="Invalid Gmail compose") as exc:
        asyncio.run(actions.create_draft({**COMPOSE, field: [recipient]}, {}, {}))
    assert "injected@example.com" not in str(exc.value)
    token.assert_not_awaited()
    assert calls == []


@pytest.mark.parametrize("change", [
    {"to": [], "cc": [], "bcc": []}, {"to": "a@example.com"}, {"subject": "Hello\nBcc: secret"},
    {"subject": "Hello\rthere"}, {"subject": "Hello\x7f"}, {"body": None},
    {"from": "spoof@example.com"}, {"From": "spoof@example.com"}, {"attachments": []},
    {"thread_id": "thread-1"}, {"to": ["a@example.com"] * 101},
])
def test_invalid_compose_rejected_before_credentials(gmail, change):
    calls, _, token = gmail
    with pytest.raises(ValueError):
        asyncio.run(actions.create_draft({**COMPOSE, **change}, {}, {}))
    token.assert_not_awaited()
    assert calls == []


@pytest.mark.parametrize("action", ["send", "send_draft"])
@pytest.mark.parametrize("confirmation", [None, False, "true", 1, "false", 0])
def test_send_requires_explicit_boolean_confirmation(gmail, action, confirmation):
    calls, _, token = gmail
    arguments = dict(COMPOSE) if action == "send" else {"draft_id": "draft-1"}
    if confirmation is not None:
        arguments["confirmed"] = confirmation
    with pytest.raises(ValueError):
        asyncio.run(getattr(actions, action)(arguments, {}, {}))
    token.assert_not_awaited()
    assert calls == []


@pytest.mark.parametrize("action", ["update_draft", "send_draft"])
@pytest.mark.parametrize("draft_id", ["", "../messages/send", "a?x=1", "a\r\nb", "a" * 201])
def test_invalid_draft_id_has_no_network(gmail, action, draft_id):
    calls, _, token = gmail
    arguments = {**COMPOSE, "draft_id": draft_id} if action == "update_draft" else {"draft_id": draft_id, "confirmed": True}
    with pytest.raises(ValueError):
        asyncio.run(getattr(actions, action)(arguments, {}, {}))
    token.assert_not_awaited()
    assert calls == []


@pytest.mark.parametrize("action", ["create_draft", "update_draft", "send", "send_draft"])
@pytest.mark.parametrize("status", [400, 401, 403, 429, 500])
def test_google_error_does_not_echo_sensitive_response(gmail, action, status):
    calls, responses, _ = gmail
    responses.append(httpx.Response(status, json={"error": {"message": "private@example.com secret-body" * 1000}}))
    arguments: dict[str, Any] = {**COMPOSE, "confirmed": True} if action == "send" else dict(COMPOSE)
    if action == "update_draft":
        arguments["draft_id"] = "draft-1"
    elif action == "send_draft":
        arguments = {"draft_id": "draft-1", "confirmed": True}
    with pytest.raises(RuntimeError) as exc:
        asyncio.run(getattr(actions, action)(arguments, {}, {}))
    assert str(status) in str(exc.value)
    assert "private@example.com" not in str(exc.value)
    assert "secret-body" not in str(exc.value)
    assert len(str(exc.value)) < 150
    assert len(calls) == 1


@pytest.mark.parametrize("response", [
    httpx.Response(200, text="private@example.com"),
    httpx.Response(200, json=[]), httpx.Response(200, json={}),
    httpx.Response(200, json={"id": "private@example.com"}),
    httpx.ReadTimeout("private@example.com secret-body"),
])
def test_uncertain_send_not_retried_and_error_is_safe(gmail, response):
    calls, responses, _ = gmail
    responses.append(response)
    with pytest.raises(RuntimeError) as exc:
        asyncio.run(actions.send({**COMPOSE, "confirmed": True}, {}, {}))
    assert "private@example.com" not in str(exc.value)
    assert "secret-body" not in str(exc.value)
    assert "retry" in str(exc.value)
    assert len(calls) == 1


def test_registry_compose_schemas_and_draft_alias(gmail):
    calls, _, _ = gmail
    registry = SkillRegistry()
    result = asyncio.run(registry.execute_action(
        skill_id="google_mail", action_name="draft", arguments=COMPOSE, config={}, context={},
    ))
    assert "create draft succeeded" in result
    assert str(calls[0].url).endswith("/drafts")
    # Inspect the registry-loaded manifest rather than a separately parsed YAML copy.
    loaded = registry.get("google_mail")
    assert loaded is not None
    declared = {action.name: action for action in loaded.manifest.actions}
    for name in ("create_draft", "update_draft", "send", "send_draft"):
        schema = declared[name].input_schema
        assert schema["additionalProperties"] is False
        assert declared[name].handler == f"actions:{name}"
        if name in ("send", "send_draft"):
            assert "confirmed" in schema["required"]
            assert schema["properties"]["confirmed"]["enum"] == [True]
    assert "draft" in declared["create_draft"].aliases
