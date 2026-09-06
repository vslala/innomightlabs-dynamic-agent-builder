import json as _json
from datetime import datetime, timedelta, timezone

from src.auth.openai_oauth import OpenAICredentials
from src.llm.providers.openai import OpenAIProvider


def test_openai_codex_request_body_uses_responses_envelope():
    provider = OpenAIProvider()

    body = provider._request_body(
        model_id="gpt-5.5",
        instructions="You are helpful.",
        request_messages=[{"role": "user", "content": "Hello"}],
        tools=[
            {
                "type": "function",
                "name": "search",
                "description": "Search records",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
    )

    assert body["model"] == "gpt-5.5"
    assert body["store"] is False
    assert body["stream"] is True
    assert body["tool_choice"] == "auto"
    assert body["parallel_tool_calls"] is False
    assert body["include"] == ["reasoning.encrypted_content"]
    assert body["text"] == {"verbosity": "medium"}
    assert body["tools"] == [
        {
            "type": "function",
            "name": "search",
            "description": "Search records",
            "parameters": {"type": "object", "properties": {}},
        }
    ]
    assert body["input"] == [
        {
            "role": "user",
            "content": [{"type": "input_text", "text": "Hello"}],
        }
    ]


def test_openai_codex_request_headers_include_account_and_sse_metadata(monkeypatch):
    provider = OpenAIProvider()
    credentials = OpenAICredentials(
        access_token="access-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        account_id="chatgpt-account-1",
    )
    monkeypatch.setattr("src.llm.providers.openai.settings.openai_oauth_originator", "codex_cli_rs")

    headers = provider._request_headers(credentials)

    assert headers["Authorization"] == "Bearer access-token"
    assert headers["Accept"] == "text/event-stream"
    assert headers["originator"] == "codex_cli_rs"
    assert headers["ChatGPT-Account-ID"] == "chatgpt-account-1"
    assert headers["session-id"]
    assert headers["thread-id"] == headers["session-id"]


def test_openai_provider_extracts_usage_defensively():
    # NOTE: field names here match the public Responses API shape
    # (response.usage.{input_tokens,output_tokens}); this has
    # not been confirmed against real traffic from the custom OAuth/Codex
    # backend. This test documents the best-effort, defensive parsing.
    event_with_usage = {
        "type": "response.completed",
        "response": {
            "usage": {
                "input_tokens": 12,
                "output_tokens": 8,
            }
        },
    }
    assert OpenAIProvider._extract_usage(event_with_usage) == (12, 8)

    # Malformed/missing shapes never raise -- they default to zeros.
    assert OpenAIProvider._extract_usage({"type": "response.completed"}) == (0, 0)
    assert OpenAIProvider._extract_usage(
        {"type": "response.completed", "response": {"usage": "not-a-dict"}}
    ) == (0, 0)
    assert OpenAIProvider._extract_usage(
        {"type": "response.completed", "response": None}
    ) == (0, 0)


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
    monkeypatch.setattr("src.llm.providers.openai.httpx.AsyncClient", FakeOpenAIAsyncClient)

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
