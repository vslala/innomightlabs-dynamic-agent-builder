from __future__ import annotations

from types import SimpleNamespace

from src.llm.providers.anthropic.chat import AnthropicProvider, mark_cache_breakpoints


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
        "src.llm.providers.anthropic.chat.AsyncAnthropic",
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


def _stream_capturing_request(monkeypatch, usage) -> dict:
    """Replace the client with one that answers with `usage` and keeps the request it was sent."""
    request: dict = {}
    stream_obj = FakeAnthropicStream(
        events=[SimpleNamespace(type="message_stop")],
        final_message=SimpleNamespace(stop_reason="end_turn", usage=usage),
    )

    def stream(**kwargs):
        request.update(kwargs)
        return stream_obj

    monkeypatch.setattr(
        "src.llm.providers.anthropic.chat.AsyncAnthropic",
        lambda api_key: SimpleNamespace(messages=SimpleNamespace(stream=stream)),
    )
    return request


async def _usage_of_a_call(**options):
    events = [
        event
        async for event in AnthropicProvider().stream_response(
            messages=[{"role": "user", "content": [{"text": "Look this up"}, {"text": "Carry on"}]}],
            credentials={"api_key": "test-key"},
            **options,
        )
    ]
    return next(event for event in events if event.type == "usage")


async def test_a_call_that_continues_a_conversation_marks_where_the_next_call_reads_the_cache(monkeypatch):
    request = _stream_capturing_request(monkeypatch, SimpleNamespace(input_tokens=1, output_tokens=1))

    await _usage_of_a_call(cache_key="conversation-1")

    newest = request["messages"][-1]["content"]
    assert [block.get("cache_control") for block in newest] == [{"type": "ephemeral"}] * 2


async def test_a_one_off_call_is_not_cached(monkeypatch):
    """Anthropic charges extra for a cache write, which a call nothing follows never reads back."""
    request = _stream_capturing_request(monkeypatch, SimpleNamespace(input_tokens=1, output_tokens=1))

    await _usage_of_a_call()

    assert not any("cache_control" in block for block in request["messages"][-1]["content"])


def test_only_the_newest_messages_last_two_blocks_are_marked():
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "Hi"}]},
        {"role": "user", "content": [{"type": "tool_result"}, {"type": "tool_result"}, {"type": "text", "text": "Go"}]},
    ]

    mark_cache_breakpoints(messages)

    assert "cache_control" not in messages[0]["content"][0]
    assert ["cache_control" in block for block in messages[1]["content"]] == [False, True, True]


async def test_the_prompt_counts_the_tokens_anthropic_read_from_and_wrote_to_the_cache(monkeypatch):
    _stream_capturing_request(monkeypatch, SimpleNamespace(
        input_tokens=10, output_tokens=20, cache_read_input_tokens=900, cache_creation_input_tokens=90,
    ))

    usage = await _usage_of_a_call(cache_key="conversation-1")

    assert (usage.prompt_tokens, usage.cache_read_tokens, usage.cache_write_tokens) == (1000, 900, 90)
