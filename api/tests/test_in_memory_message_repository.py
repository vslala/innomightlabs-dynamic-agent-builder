from __future__ import annotations

from src.messages.models import Message
from src.messages.repositories.in_memory import InMemoryMessageRepository


class FakeCompactionStrategy:
    def __init__(self):
        self.calls = []

    def compact(self, *, conversation_id: str, messages: list[Message], target_tokens: int) -> Message:
        self.calls.append(
            {
                "conversation_id": conversation_id,
                "message_count": len(messages),
                "target_tokens": target_tokens,
            }
        )
        return Message(
            conversation_id=conversation_id,
            created_by="owner@example.com",
            role="user",
            content="Compacted summary preserving id=abc123 and next steps.",
        )


def test_in_memory_repository_compacts_when_context_exceeds_limit():
    strategy = FakeCompactionStrategy()
    repository = InMemoryMessageRepository(compaction_strategy=strategy)
    repository.context_token_limit = 20

    repository.save(
        Message(
            conversation_id="conv-1",
            created_by="owner@example.com",
            role="user",
            content="Find details for id=abc123 and keep exact values.",
        )
    )
    repository.save(
        Message(
            conversation_id="conv-1",
            created_by="owner@example.com",
            role="assistant",
            content="Fetched a long result that pushes the in-memory context over budget.",
        )
    )

    messages = repository.find_by_conversation("conv-1")

    assert len(messages) == 1
    assert messages[0].content == "Compacted summary preserving id=abc123 and next steps."
    assert strategy.calls == [
        {
                "conversation_id": "conv-1",
                "message_count": 2,
                "target_tokens": 6,
            }
        ]
    assert repository.count_by_conversation("conv-1") == 1


def test_in_memory_repository_does_not_compact_on_read():
    strategy = FakeCompactionStrategy()
    repository = InMemoryMessageRepository(compaction_strategy=strategy)
    repository.context_token_limit = 1_000_000

    repository.save(
        Message(
            conversation_id="conv-1",
            created_by="owner@example.com",
            role="user",
            content="Short message.",
        )
    )

    repository.context_token_limit = 1
    messages = repository.find_by_conversation("conv-1")

    assert len(messages) == 1
    assert messages[0].content == "Short message."
    assert strategy.calls == []


def test_in_memory_repository_does_not_compact_on_write_when_context_is_under_limit():
    strategy = FakeCompactionStrategy()
    repository = InMemoryMessageRepository(compaction_strategy=strategy)

    repository.save(
        Message(
            conversation_id="conv-1",
            created_by="owner@example.com",
            role="user",
            content="Short message.",
        )
    )

    messages = repository.find_by_conversation("conv-1")

    assert len(messages) == 1
    assert messages[0].content == "Short message."
    assert strategy.calls == []
