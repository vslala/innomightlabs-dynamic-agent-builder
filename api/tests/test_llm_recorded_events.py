"""What a stored invocation keeps from a live event stream."""

from src.llm.events import (
    MAX_RECORDED_EVENT_CONTENT_CHARS,
    RECORDED_CONTENT_TRUNCATION_MARKER,
    SSEEvent,
    SSEEventType,
    recorded_events,
)


def make_stream() -> list[SSEEvent]:
    """A stream shaped like a real agent turn: deltas around two tool calls."""
    return [
        SSEEvent(event_type=SSEEventType.LIFECYCLE_NOTIFICATION, content="Thinking..."),
        SSEEvent(event_type=SSEEventType.AGENT_THOUGHTS, content="I should search the mailbox"),
        SSEEvent(
            event_type=SSEEventType.TOOL_CALL_START,
            content="",
            tool_name="gmail_search",
            tool_args={"query": "is:unread"},
        ),
        SSEEvent(
            event_type=SSEEventType.TOOL_CALL_RESULT,
            content='{"messages": []}',
            tool_name="gmail_search",
            success=True,
        ),
        *[
            SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content=chunk)
            for chunk in ("You ", "have ", "no ", "unread ", "mail.")
        ],
        SSEEvent(event_type=SSEEventType.TOKEN_USAGE_UPDATE, content="", total_tokens=1234),
        SSEEvent(event_type=SSEEventType.ASSISTANT_MESSAGE_SAVED, content="", message_id="m-1"),
        SSEEvent(event_type=SSEEventType.STREAM_COMPLETE, content=""),
    ]


def test_keeps_only_tool_calls():
    kept = recorded_events(make_stream())

    assert [event["event_type"] for event in kept] == ["TOOL_CALL_START", "TOOL_CALL_RESULT"]


def test_keeps_the_fields_the_run_inspector_pairs():
    kept = recorded_events(make_stream())

    start, result = kept
    assert start["tool_name"] == "gmail_search"
    assert start["tool_args"] == {"query": "is:unread"}
    assert result["content"] == '{"messages": []}'
    assert result["success"] is True


def test_drops_response_deltas_that_response_text_already_holds():
    kept = recorded_events(make_stream())

    assert all(event["event_type"] != "AGENT_RESPONSE_TO_USER" for event in kept)


def test_empty_stream_and_stream_with_no_tool_calls():
    assert recorded_events([]) == []
    assert (
        recorded_events(
            [SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content="hello")]
        )
        == []
    )


def test_caps_an_oversized_tool_result():
    oversized = "x" * (MAX_RECORDED_EVENT_CONTENT_CHARS + 5_000)
    kept = recorded_events(
        [
            SSEEvent(
                event_type=SSEEventType.TOOL_CALL_RESULT,
                content=oversized,
                tool_name="scrape",
            )
        ]
    )

    content = kept[0]["content"]
    assert content.endswith(RECORDED_CONTENT_TRUNCATION_MARKER)
    assert len(content) == MAX_RECORDED_EVENT_CONTENT_CHARS + len(
        RECORDED_CONTENT_TRUNCATION_MARKER
    )


def test_leaves_content_within_the_cap_untouched():
    kept = recorded_events(
        [SSEEvent(event_type=SSEEventType.TOOL_CALL_RESULT, content="small", tool_name="t")]
    )

    assert kept[0]["content"] == "small"


def test_a_long_turn_stays_small():
    """The failure mode this guards: a long turn used to persist every delta."""
    chatty = [
        SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content="word ")
        for _ in range(4_000)
    ]
    assert recorded_events(chatty) == []
