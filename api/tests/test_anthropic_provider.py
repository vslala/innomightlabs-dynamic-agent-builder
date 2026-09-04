from __future__ import annotations

import pytest

from src.llm import credentials as credential_loader
from src.llm.providers.anthropic import AnthropicProvider
from src.llm.credentials import ANTHROPIC_OAUTH_BETA, mint_anthropic_oauth_access_token


def test_anthropic_provider_adds_type_to_bedrock_style_text_blocks() -> None:
    provider = AnthropicProvider()

    request_input = provider._extract_system_and_messages(
        [
            {"role": "system", "content": [{"text": "System prompt"}]},
            {
                "role": "assistant",
                "content": [{"text": "I will inspect that."}],
            },
        ]
    )

    assert request_input.system_prompt == "System prompt"
    assert request_input.messages == [
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "I will inspect that."}],
        }
    ]


def test_anthropic_provider_converts_bedrock_tool_blocks() -> None:
    provider = AnthropicProvider()

    request_input = provider._extract_system_and_messages(
        [
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tool_123",
                            "name": "execute_skill_action",
                            "input": {"skill_id": "aws_cli"},
                        }
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": "tool_123",
                            "content": [{"text": '{"ok": true}'}],
                        }
                    }
                ],
            },
        ]
    )

    assert request_input.messages == [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tool_123",
                    "name": "execute_skill_action",
                    "input": {"skill_id": "aws_cli"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tool_123",
                    "content": '{"ok": true}',
                }
            ],
        },
    ]


def test_anthropic_provider_uses_oauth_client_for_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class FakeAsyncAnthropic:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("src.llm.providers.anthropic.AsyncAnthropic", FakeAsyncAnthropic)

    client = AnthropicProvider()._create_client({"access_token": "access-token"})

    assert isinstance(client, FakeAsyncAnthropic)
    assert captured == {
        "auth_token": "access-token",
        "default_headers": {"anthropic-beta": ANTHROPIC_OAUTH_BETA},
    }


@pytest.mark.asyncio
async def test_mint_anthropic_oauth_access_token_uses_refresh_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"access_token": "minted-access-token"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def post(self, url: str, **kwargs) -> FakeResponse:
            captured["url"] = url
            captured.update(kwargs)
            return FakeResponse()

    monkeypatch.setattr(credential_loader.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    result = await mint_anthropic_oauth_access_token(
        {"refresh_token": "refresh-token", "client_id": "client-id"}
    )

    assert result == {"access_token": "minted-access-token"}
    assert captured["url"] == "https://platform.claude.com/v1/oauth/token"
    assert captured["headers"] == {
        "Content-Type": "application/json",
        "anthropic-beta": ANTHROPIC_OAUTH_BETA,
    }
    assert captured["json"] == {
        "grant_type": "refresh_token",
        "refresh_token": "refresh-token",
        "client_id": "client-id",
    }
