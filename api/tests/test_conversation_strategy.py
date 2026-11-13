from datetime import datetime, timedelta, timezone

from src.llm.conversation_strategy import FixedWindowStrategy, sent_at
from src.messages.models import Message, MessageImage


def test_fixed_window_strategy_excludes_system_messages():
    hello = Message(conversation_id="conv-1", role="user", content="hello")
    messages = [
        hello,
        Message(
            conversation_id="conv-1",
            role="system",
            content='{"type":"tool_call_audit","result":"hidden"}',
        ),
        Message(conversation_id="conv-1", role="assistant", content="hi"),
    ]

    context = FixedWindowStrategy(max_words=100).build_context(messages)

    assert context == [
        {"role": "user", "content": f"{sent_at(hello)}\nhello"},
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


def test_a_generated_image_keeps_its_id_in_later_turns():
    image = MessageImage(image_id="img-1", s3_key="k", filename="generated-image-1.png", mime_type="image/png",
                         size_bytes=10, width=1024, height=1024, prompt="A lighthouse at dawn")
    messages = [
        Message(conversation_id="conv-1", role="assistant", content="Generated image: A lighthouse", images=[image]),
        post_it := Message(conversation_id="conv-1", role="user", content="post it"),
    ]

    context = FixedWindowStrategy(max_words=200).build_context(messages)

    assert context[0]["content"].startswith("Generated image: A lighthouse")
    assert '<generated_image id="img-1" filename="generated-image-1.png" size="1024x1024">' in context[0]["content"]
    assert "Prompt: A lighthouse at dawn" in context[0]["content"]
    assert context[1] == {"role": "user", "content": f"{sent_at(post_it)}\npost it"}


def test_each_user_message_says_when_it_was_sent_and_reads_the_same_on_every_later_call():
    """The time rides on the message, not the system prompt, so the history a vendor cached keeps matching."""
    sent = datetime(2026, 11, 13, 13, 37, tzinfo=timezone.utc)
    messages = [
        Message(conversation_id="conv-1", role="user", content="post it", created_at=sent),
        Message(conversation_id="conv-1", role="assistant", content="Posted.", created_at=sent + timedelta(minutes=1)),
    ]

    first = FixedWindowStrategy(max_words=100).build_context(messages)
    later = FixedWindowStrategy(max_words=100).build_context(messages)

    assert first[0]["content"] == "[Sent Friday, November 13, 2026 at 01:37 PM UTC]\npost it"
    assert first[1]["content"] == "Posted.", "a reply carries no time, or the model starts writing them"
    assert later == first


def test_a_time_stored_without_a_zone_is_read_as_utc():
    message = Message(conversation_id="conv-1", role="user", content="hi", created_at=datetime(2026, 11, 13, 9, 5))

    assert sent_at(message) == "[Sent Friday, November 13, 2026 at 09:05 AM UTC]"
