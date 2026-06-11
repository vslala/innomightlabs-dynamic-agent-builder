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
