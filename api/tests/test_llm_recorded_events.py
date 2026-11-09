"""What a stored invocation keeps from a live event stream."""

from datetime import datetime, timezone

from src.llm.events import (
    MAX_RECORDED_EVENT_CONTENT_CHARS,
    RECORDED_CONTENT_TRUNCATION_MARKER,
    SSEEvent,
    SSEEventType,
    capped_events,
    tool_call_events,
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
    kept = tool_call_events(make_stream())

    assert [event["event_type"] for event in kept] == ["TOOL_CALL_START", "TOOL_CALL_RESULT"]


def test_keeps_the_fields_the_run_inspector_pairs():
    kept = tool_call_events(make_stream())

    start, result = kept
    assert start["tool_name"] == "gmail_search"
    assert start["tool_args"] == {"query": "is:unread"}
    assert result["content"] == '{"messages": []}'
    assert result["success"] is True


def test_drops_response_deltas_that_response_text_already_holds():
    kept = tool_call_events(make_stream())

    assert all(event["event_type"] != "AGENT_RESPONSE_TO_USER" for event in kept)


def test_empty_stream_and_stream_with_no_tool_calls():
    assert tool_call_events([]) == []
    assert (
        tool_call_events(
            [SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content="hello")]
        )
        == []
    )


def test_keeps_an_oversized_tool_result_whole():
    oversized = "x" * (MAX_RECORDED_EVENT_CONTENT_CHARS + 5_000)
    kept = tool_call_events(
        [SSEEvent(event_type=SSEEventType.TOOL_CALL_RESULT, content=oversized, tool_name="scrape")]
    )

    assert kept[0]["content"] == oversized


def test_keeps_when_the_tool_ran():
    started = datetime(2026, 11, 9, 9, 0, 1, tzinfo=timezone.utc)
    completed = datetime(2026, 11, 9, 9, 0, 3, tzinfo=timezone.utc)
    kept = tool_call_events(
        [
            SSEEvent(
                event_type=SSEEventType.TOOL_CALL_RESULT,
                content="{}",
                tool_call_id="tc_1",
                started_at=started,
                completed_at=completed,
            )
        ]
    )

    assert kept[0]["tool_call_id"] == "tc_1"
    assert kept[0]["started_at"] == "2026-11-09T09:00:01Z"
    assert kept[0]["completed_at"] == "2026-11-09T09:00:03Z"


def test_caps_an_oversized_tool_result_for_an_inline_copy():
    oversized = "x" * (MAX_RECORDED_EVENT_CONTENT_CHARS + 5_000)
    original = tool_call_events(
        [SSEEvent(event_type=SSEEventType.TOOL_CALL_RESULT, content=oversized, tool_name="scrape")]
    )
    kept = capped_events(original)

    content = kept[0]["content"]
    assert content.endswith(RECORDED_CONTENT_TRUNCATION_MARKER)
    assert len(content) == MAX_RECORDED_EVENT_CONTENT_CHARS + len(
        RECORDED_CONTENT_TRUNCATION_MARKER
    )
    assert original[0]["content"] == oversized, "capping copies; the whole log is untouched"


def test_leaves_content_within_the_cap_untouched():
    kept = capped_events(
        tool_call_events([SSEEvent(event_type=SSEEventType.TOOL_CALL_RESULT, content="small", tool_name="t")])
    )

    assert kept[0]["content"] == "small"


def test_a_long_turn_stays_small():
    """The failure mode this guards: a long turn used to persist every delta."""
    chatty = [
        SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content="word ")
        for _ in range(4_000)
    ]
    assert tool_call_events(chatty) == []
