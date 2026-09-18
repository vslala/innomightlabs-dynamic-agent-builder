from datetime import datetime, timezone
from typing import Literal

import pytest

from src.dream.sessions import DreamSession, SessionChunker, split_into_exchanges
from src.messages.models import Message


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def message(
    message_id: str, role: Literal["user", "assistant", "system"], content: str
) -> Message:
    return Message(
        message_id=message_id,
        conversation_id="conversation-1",
        role=role,
        content=content,
        created_at=NOW,
    )


def session(messages: list[Message]) -> DreamSession:
    return DreamSession("conversation-1", "Test", messages)


def test_split_into_exchanges_pairs_user_with_assistant_reply():
    messages = [message("u1", "user", "question"), message("a1", "assistant", "answer")]

    assert [exchange.messages for exchange in split_into_exchanges(messages)] == [messages]


def test_split_into_exchanges_supports_tool_only_turn_and_consecutive_users():
    messages = [
        message("u1", "user", "first"),
        message("u2", "user", "second"),
        message("a2", "assistant", "reply"),
    ]

    exchanges = split_into_exchanges(messages)

    assert [exchange.messages for exchange in exchanges] == [[messages[0]], messages[1:]]


def test_split_into_exchanges_preserves_a_leading_assistant_message():
    messages = [message("a0", "assistant", "opening"), message("u1", "user", "question")]

    assert [exchange.messages for exchange in split_into_exchanges(messages)] == [[messages[0]], [messages[1]]]


def test_fitting_session_is_one_session_chunk():
    messages = [message("u1", "user", "I am vegetarian")]

    chunks = SessionChunker().chunk(session(messages), max_words=3, window_overlap_words=1)

    assert len(chunks) == 1
    assert chunks[0].granularity == "session"
    assert chunks[0].messages == messages


def test_oversized_session_packs_whole_exchanges_without_splitting_them():
    messages = [
        message("u1", "user", "one two"),
        message("a1", "assistant", "three four"),
        message("u2", "user", "five six"),
        message("a2", "assistant", "seven eight"),
    ]

    chunks = SessionChunker().chunk(session(messages), max_words=4, window_overlap_words=1)

    assert [chunk.granularity for chunk in chunks] == ["exchange_group", "exchange_group"]
    assert [chunk.messages for chunk in chunks] == [messages[:2], messages[2:]]


def test_oversized_exchange_descends_to_messages():
    messages = [message("u1", "user", "one two three"), message("a1", "assistant", "four five six")]

    chunks = SessionChunker().chunk(session(messages), max_words=3, window_overlap_words=1)

    assert [chunk.granularity for chunk in chunks] == ["message", "message"]
    assert [chunk.messages for chunk in chunks] == [[messages[0]], [messages[1]]]


def test_oversized_message_uses_overlapping_word_windows_losslessly():
    original = message("u1", "user", "one two three four five six seven")

    chunks = SessionChunker().chunk(session([original]), max_words=3, window_overlap_words=1)

    assert [chunk.granularity for chunk in chunks] == ["window", "window", "window", "window"]
    assert [chunk.window_index for chunk in chunks] == [0, 1, 2, 3]
    assert all(chunk.window_total == 4 for chunk in chunks)
    windows = [chunk.messages[0].content.split() for chunk in chunks]
    restored = windows[0] + [word for window in windows[1:] for word in window[1:]]
    assert restored == original.content.split()


def test_short_user_message_is_never_filtered():
    short = message("u1", "user", "I code")

    assert SessionChunker().chunk(session([short]), max_words=100, window_overlap_words=1)[0].messages == [short]


@pytest.mark.parametrize("max_words, overlap", [(0, 0), (1, 1), (2, -1)])
def test_chunker_requires_a_progressing_positive_window(max_words: int, overlap: int):
    with pytest.raises(ValueError):
        SessionChunker().chunk(session([message("u1", "user", "hello")]), max_words, overlap)
