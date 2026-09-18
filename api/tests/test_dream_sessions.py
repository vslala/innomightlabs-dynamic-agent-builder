from datetime import datetime, timedelta, timezone
from typing import Literal

import pytest

from src.dream.sessions import SessionSegmenter
from src.messages.models import Message


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def message(role: Literal["user", "assistant", "system"], minutes: int) -> Message:
    return Message(
        message_id=f"{role}-{minutes}",
        conversation_id="conversation-1",
        role=role,
        content=f"{role} message",
        created_at=BASE + timedelta(minutes=minutes),
    )


def segment(messages: list[Message], timeout: int = 60):
    return SessionSegmenter().segment("conversation-1", "Test", messages, timeout)


def test_segments_a_continuous_conversation_into_one_session():
    sessions = segment([message("user", 0), message("assistant", 59), message("user", 60)])

    assert len(sessions) == 1
    assert sessions[0].messages == [message("user", 0), message("assistant", 59), message("user", 60)]


def test_gap_at_exact_timeout_stays_in_the_same_session():
    sessions = segment([message("user", 0), message("assistant", 60)])

    assert len(sessions) == 1


def test_gap_larger_than_timeout_starts_a_new_session():
    sessions = segment(
        [message("user", 0), message("assistant", 5), message("user", 66), message("assistant", 130)]
    )

    assert [[item.created_at for item in session.messages] for session in sessions] == [
        [BASE, BASE + timedelta(minutes=5)],
        [BASE + timedelta(minutes=66)],
    ]


def test_zero_timeout_keeps_the_full_conversation_together():
    messages = [message("user", 0), message("assistant", 500)]

    sessions = segment(messages, timeout=0)

    assert len(sessions) == 1
    assert sessions[0].messages == messages


def test_drops_system_messages_and_assistant_only_sessions():
    sessions = segment(
        [
            message("assistant", 0),
            message("system", 1),
            message("user", 120),
            message("assistant", 121),
        ]
    )

    assert len(sessions) == 1
    assert [item.role for item in sessions[0].messages] == ["user", "assistant"]


def test_empty_input_has_no_sessions():
    assert segment([]) == []


def test_rejects_messages_not_in_chronological_order():
    with pytest.raises(AssertionError, match="sorted ascending"):
        segment([message("user", 2), message("assistant", 1)])
