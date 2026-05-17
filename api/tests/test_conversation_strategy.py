from datetime import datetime, timedelta, timezone

from src.llm.conversation_strategy import FixedWindowStrategy
from src.messages.models import Message


def test_fixed_window_strategy_excludes_system_messages():
    messages = [
        Message(conversation_id="conv-1", role="user", content="hello"),
        Message(
            conversation_id="conv-1",
            role="system",
            content='{"type":"tool_call_audit","result":"hidden"}',
        ),
        Message(conversation_id="conv-1", role="assistant", content="hi"),
    ]

    context = FixedWindowStrategy(max_words=100).build_context(messages)

    assert context == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_fixed_window_strategy_timeout_ignores_latest_system_message():
    now = datetime.now(timezone.utc)
    messages = [
        Message(
            conversation_id="conv-1",
            role="user",
            content="old user message",
            created_at=now - timedelta(hours=2),
        ),
        Message(
            conversation_id="conv-1",
            role="assistant",
            content="old assistant message",
            created_at=now - timedelta(hours=2),
        ),
        Message(
            conversation_id="conv-1",
            role="system",
            content='{"type":"tool_call_audit"}',
            created_at=now,
        ),
    ]

    context = FixedWindowStrategy(max_words=100).build_context(
        messages,
        session_timeout_minutes=60,
    )

    assert context == []
