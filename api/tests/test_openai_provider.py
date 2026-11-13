import json as _json
from datetime import datetime, timedelta, timezone

import pytest

from src.auth.openai_oauth import OpenAICredentials
from src.llm.providers.openai.chat import CODEX_EXTRAS, OpenAIProvider, codex_headers
from src.llm.wire.responses import responses_body


def test_the_codex_body_carries_reasoning_between_turns():
    body = responses_body("gpt-5.5", [{"role": "user", "content": "Hello"}], None, **CODEX_EXTRAS)

    assert body["include"] == ["reasoning.encrypted_content"]
    assert body["text"] == {"verbosity": "medium"}
    assert body["reasoning"] is None


def test_openai_codex_request_headers_include_account_and_sse_metadata(monkeypatch):
    credentials = OpenAICredentials(
        access_token="access-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        account_id="chatgpt-account-1",
    )
    monkeypatch.setattr("src.llm.providers.openai.chat.settings.openai_oauth_originator", "codex_cli_rs")

    headers = codex_headers(credentials)

    assert headers["Authorization"] == "Bearer access-token"
    assert headers["Accept"] == "text/event-stream"
    assert headers["originator"] == "codex_cli_rs"
    assert headers["ChatGPT-Account-ID"] == "chatgpt-account-1"
    assert headers["session-id"]
    assert headers["thread-id"] == headers["session-id"]


def test_a_call_that_continues_a_conversation_keeps_its_codex_session():
    credentials = OpenAICredentials(access_token="t", expires_at=datetime.now(timezone.utc) + timedelta(hours=1))

    assert codex_headers(credentials, session_id="conversation-1")["session-id"] == "conversation-1"
    assert codex_headers(credentials)["session-id"] != codex_headers(credentials)["session-id"]


class FakeOpenAIStreamResponse:
    def __init__(self, lines: list[str]):
        self.headers: dict[str, str] = {}
        self._lines = lines

    @property
    def is_success(self) -> bool:
        return True

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return b""


class FakeOpenAIStreamContext:
    def __init__(self, response: FakeOpenAIStreamResponse):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc_info):
        return False


class FakeOpenAIAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def stream(self, method, url, headers=None, json=None):
        completed_event = {
            "type": "response.completed",
            "response": {
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 8,
                }
            },
        }
        return FakeOpenAIStreamContext(
            FakeOpenAIStreamResponse(
                ["data: " + _json.dumps(completed_event), "data: [DONE]"]
            )
        )


async def test_openai_provider_yields_usage_event_from_response_completed(monkeypatch):
    monkeypatch.setattr("src.llm.wire.responses.httpx.AsyncClient", FakeOpenAIAsyncClient)

    provider = OpenAIProvider()
    credentials = {
        "access_token": "token",
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "account_id": "acct-1",
    }

    events = [
        event
        async for event in provider.stream_response(
            messages=[{"role": "user", "content": "hi"}],
            credentials=credentials,
            tools=None,
            model="gpt-5.5",
        )
    ]

    usage_events = [event for event in events if event.type == "usage"]
    assert len(usage_events) == 1
    assert usage_events[0].prompt_tokens == 12
    assert usage_events[0].completion_tokens == 8


def _stream_of(*events):
    class Client(FakeOpenAIAsyncClient):
        def stream(self, method, url, headers=None, json=None):
            return FakeOpenAIStreamContext(
                FakeOpenAIStreamResponse(["data: " + _json.dumps(event) for event in events] + ["data: [DONE]"])
            )

    return Client


async def _events(monkeypatch, *stream_events):
    monkeypatch.setattr("src.llm.wire.responses.httpx.AsyncClient", _stream_of(*stream_events))
    credentials = {
        "access_token": "token",
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "account_id": "acct-1",
    }
    return [
        event
        async for event in OpenAIProvider().stream_response(
            messages=[{"role": "user", "content": "hi"}], credentials=credentials, tools=None, model="gpt-5.5"
        )
    ]


async def test_an_incomplete_codex_response_says_the_model_was_cut_off(monkeypatch):
    events = await _events(
        monkeypatch,
        {"type": "response.incomplete", "response": {"incomplete_details": {"reason": "max_output_tokens"}}},
    )

    assert [(event.type, event.content) for event in events][-1] == ("stop", "max_tokens")


async def test_a_completed_codex_response_is_a_normal_end(monkeypatch):
    events = await _events(monkeypatch, {"type": "response.completed", "response": {}})

    assert [(event.type, event.content) for event in events][-1] == ("stop", "end_turn")


async def test_a_failed_codex_response_raises_instead_of_ending_silently(monkeypatch):
    with pytest.raises(RuntimeError, match="OpenAI OAuth response failed"):
        await _events(monkeypatch, {"type": "response.failed", "response": {"error": {"code": "server_error"}}})
