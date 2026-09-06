from __future__ import annotations

from types import SimpleNamespace

from src.llm.providers.anthropic import AnthropicProvider


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


class FakeAnthropicStream:
    """Fakes the async context manager + async iterator returned by
    client.messages.stream(...)."""

    def __init__(self, events, final_message):
        self._events = events
        self._final_message = final_message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for event in self._events:
            yield event

    async def get_final_message(self):
        return self._final_message


async def test_anthropic_provider_yields_usage_event_from_final_message(monkeypatch) -> None:
    final_message = SimpleNamespace(
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=10, output_tokens=20),
    )
    stream_obj = FakeAnthropicStream(
        events=[SimpleNamespace(type="message_stop")],
        final_message=final_message,
    )
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(stream=lambda **kwargs: stream_obj)
    )
    monkeypatch.setattr(
        "src.llm.providers.anthropic.AsyncAnthropic",
        lambda api_key: fake_client,
    )

    provider = AnthropicProvider()
    events = [
        event
        async for event in provider.stream_response(
            messages=[{"role": "user", "content": "hi"}],
            credentials={"api_key": "test-key"},
            tools=None,
            model="claude-sonnet-4-5",
        )
    ]

    usage_events = [event for event in events if event.type == "usage"]
    assert len(usage_events) == 1
    assert usage_events[0].prompt_tokens == 10
    assert usage_events[0].completion_tokens == 20
