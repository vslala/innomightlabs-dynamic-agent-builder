"""The Responses API wire format shared by the providers that speak it."""

import json

import pytest

from src.llm.providers.openai.chat import CODEX_EXTRAS
from src.llm.wire.responses import bearer_headers, responses_body, responses_input, stream_chat, usage_event
from src.llm.wire.sse import sse_events

SEARCH_TOOL = {
    "type": "function",
    "name": "search",
    "description": "Search records",
    "parameters": {"type": "object", "properties": {}},
}


def test_the_body_is_a_streamed_unstored_request_with_one_tool_call_at_a_time():
    body = responses_body("gpt-5.5", [{"role": "user", "content": "Hello"}], [SEARCH_TOOL], **CODEX_EXTRAS)

    # Exactly the body OpenAIProvider sent before the wire format was shared
    assert body == {
        "model": "gpt-5.5",
        "instructions": "You are a helpful assistant.",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "Hello"}]}],
        "tools": [SEARCH_TOOL],
        "tool_choice": "auto",
        "parallel_tool_calls": True,
        "reasoning": None,
        "store": False,
        "stream": True,
        "include": ["reasoning.encrypted_content"],
        "text": {"verbosity": "medium"},
    }


def test_a_backend_without_extras_sends_only_the_common_body():
    body = responses_body("grok-4.7", [{"role": "user", "content": "Hello"}], None)

    assert not {"include", "text", "reasoning"} & body.keys()


def test_the_system_message_becomes_the_instructions():
    instructions, items = responses_input([{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hi"}])

    assert instructions == "Be brief."
    assert items == [{"role": "user", "content": [{"type": "input_text", "text": "Hi"}]}]


def test_tool_calls_go_as_function_calls_not_text():
    """Text-encoded calls taught the model to type its next call, which ended long tool runs with no answer."""
    context = [
        {"role": "user", "content": "Update PROJ-1"},
        {
            "role": "assistant",
            "content": [
                {"text": "Updating it now."},
                {"toolUse": {"toolUseId": "call_1", "name": "call_mcp_tool", "input": {"tool_name": "editJiraIssue"}}},
            ],
        },
        {"role": "user", "content": [{"toolResult": {"toolUseId": "call_1", "content": [{"text": '{"ok": true}'}]}}]},
        {"role": "user", "content": [{"text": "Continue."}]},
    ]

    _, items = responses_input(context)

    assert items == [
        {"role": "user", "content": [{"type": "input_text", "text": "Update PROJ-1"}]},
        {"role": "assistant", "content": [{"type": "output_text", "text": "Updating it now."}]},
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "call_mcp_tool",
            "arguments": '{"tool_name": "editJiraIssue"}',
        },
        {"type": "function_call_output", "call_id": "call_1", "output": '{"ok": true}'},
        {"role": "user", "content": [{"type": "input_text", "text": "Continue."}]},
    ]


def test_a_large_tool_result_goes_whole():
    result = "x" * 250_000
    context = [
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": "call_1", "name": "search", "input": {}}}]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": "call_1", "content": [{"text": result}]}}]},
    ]

    _, items = responses_input(context)

    assert items[-1]["output"] == result


def _completed(usage):
    return {"type": "response.completed", "response": {"usage": usage}}


def test_usage_counts_every_input_token_and_says_how_many_the_cache_served():
    usage = usage_event(_completed({
        "input_tokens": 1000,
        "output_tokens": 8,
        "input_tokens_details": {"cached_tokens": 900, "cache_write_tokens": 50},
    }))

    assert (usage.prompt_tokens, usage.completion_tokens) == (1000, 8)
    assert (usage.cache_read_tokens, usage.cache_write_tokens) == (900, 50)


def test_usage_is_read_defensively():
    def counts(event):
        usage = usage_event(event)
        return usage.prompt_tokens, usage.completion_tokens, usage.cache_read_tokens

    assert counts(_completed({"input_tokens": 12, "output_tokens": 8})) == (12, 8, 0)
    # Shapes the vendor might change never raise: usage is telemetry.
    assert counts({"type": "response.completed"}) == (0, 0, 0)
    assert counts(_completed("not-a-dict")) == (0, 0, 0)
    assert counts(_completed({"input_tokens": "many"})) == (0, 0, 0)
    assert counts({"type": "response.completed", "response": None}) == (0, 0, 0)
    assert counts({"type": "response.completed", "response": "text"}) == (0, 0, 0)


def test_a_call_that_continues_a_conversation_names_it_for_the_vendors_cache():
    hello = [{"role": "user", "content": "Hello"}]

    assert responses_body("grok-4.7", hello, None, cache_key="conversation-1")["prompt_cache_key"] == "conversation-1"
    assert "prompt_cache_key" not in responses_body("grok-4.7", hello, None)


def test_an_api_key_vendor_is_called_with_the_key_as_a_bearer_token():
    assert bearer_headers({"api_key": "sk-test"})["Authorization"] == "Bearer sk-test"
    with pytest.raises(ValueError, match="api_key"):
        bearer_headers({})


class Lines:
    def __init__(self, *lines: str):
        self.lines = lines

    async def aiter_lines(self):
        for line in self.lines:
            yield line


async def test_sse_events_are_the_json_objects_of_the_data_lines():
    response = Lines(
        ": keep-alive",
        "event: response.created",
        f"data: {json.dumps({'type': 'response.created'})}",
        "data: not json",
        "data: [1, 2]",
        "",
        "data: [DONE]",
    )

    assert [event async for event in sse_events(response)] == [{"type": "response.created"}]



class StreamedEvents:
    """httpx.AsyncClient for one streamed call that answers with these Responses events."""

    def __init__(self, events: list[dict]):
        self.events = events
        self.headers: dict[str, str] = {}
        self.is_success = True

    def __call__(self, *args, **kwargs):
        return self

    def stream(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def aiter_lines(self):
        for event in self.events:
            yield "data: " + json.dumps(event)


def _function_call(item_id: str, call_id: str, arguments: str) -> list[dict]:
    return [
        {"type": "response.output_item.added", "item": {"type": "function_call", "id": item_id, "call_id": call_id, "name": "get_commit"}},
        {"type": "response.function_call_arguments.delta", "item_id": item_id, "delta": arguments},
        {"type": "response.function_call_arguments.done", "item_id": item_id},
    ]


async def test_a_response_with_several_function_calls_streams_each_so_the_loop_runs_them_as_one_batch(monkeypatch):
    events = [*_function_call("item-1", "call-1", '{"sha": "a1"}'), *_function_call("item-2", "call-2", '{"sha": "b2"}')]
    monkeypatch.setattr("src.llm.wire.responses.httpx.AsyncClient", StreamedEvents([*events, {"type": "response.completed"}]))

    tool_uses = [
        (event.tool_use_id, event.tool_input)
        async for event in stream_chat("https://vendor.example/responses", {}, {"input": []}, label="Test")
        if event.type == "tool_use"
    ]

    assert tool_uses == [("call-1", {"sha": "a1"}), ("call-2", {"sha": "b2"})]
