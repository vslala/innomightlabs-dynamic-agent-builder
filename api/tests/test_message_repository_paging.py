"""Regression tests for the conversation-context read path.

See api/docs/LLD-agent-runtime-refactor.md (P0.1). Both behaviours here were
broken: a conversation larger than DynamoDB's 1MB query page was silently
truncated, and tool-call audit rows shared the MESSAGE# prefix so they filled
that page with content nothing on the context path ever reads.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.messages.models import Message, MessageKind
from src.messages.repositories.dynamodb import DynamoDBMessageRepository


@pytest.fixture
def message_repository(dynamodb_table):
    return DynamoDBMessageRepository()


def _chat(conversation_id: str, index: int, *, content: str) -> Message:
    return Message(
        conversation_id=conversation_id,
        role="user",
        content=content,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=index),
    )


def test_find_by_conversation_returns_messages_beyond_one_query_page(message_repository):
    """A single DynamoDB query returns at most 1MB; the rest must not vanish."""
    # 40 x 40KB is comfortably over the page limit, so the first query can only
    # answer part of it and has to be followed by LastEvaluatedKey.
    for index in range(40):
        message_repository.save(_chat("big", index, content="x" * 40_000))

    found = message_repository.find_by_conversation("big")

    assert len(found) == 40
    assert [m.content[0] for m in found] == ["x"] * 40


def test_find_by_conversation_is_ordered_oldest_first_across_pages(message_repository):
    for index in range(40):
        message_repository.save(_chat("ordered", index, content=f"{index:03d}" + "y" * 40_000))

    found = message_repository.find_by_conversation("ordered")

    assert [m.content[:3] for m in found] == [f"{i:03d}" for i in range(40)]


def test_audit_rows_never_reach_the_conversation_context(message_repository):
    message_repository.save(_chat("split", 0, content="Hello"))
    message_repository.save(
        Message(
            conversation_id="split",
            role="system",
            content='{"type":"tool_call_audit"}',
            kind=MessageKind.TOOL_AUDIT,
            created_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        )
    )

    context = message_repository.find_by_conversation("split")
    audit, _, _ = message_repository.find_audit_by_conversation("split")

    assert [m.content for m in context] == ["Hello"]
    assert [m.content for m in audit] == ['{"type":"tool_call_audit"}']


def test_audit_rows_are_deleted_with_the_conversation(message_repository):
    message_repository.save(_chat("purge", 0, content="Hello"))
    message_repository.save(
        Message(
            conversation_id="purge",
            role="system",
            content="audit",
            kind=MessageKind.TOOL_AUDIT,
        )
    )

    assert message_repository.delete_by_conversation("purge") == 2
    assert message_repository.find_by_conversation("purge") == []
    assert message_repository.find_audit_by_conversation("purge")[0] == []


def test_legacy_rows_without_a_kind_load_as_chat(message_repository, dynamodb_table):
    """Rows written before the AUDIT# split have no `kind` attribute."""
    legacy = _chat("legacy", 0, content="written before the split")
    item = legacy.to_dynamo_item()
    del item["kind"]
    dynamodb_table.put_item(Item=item)

    found = message_repository.find_by_conversation("legacy")

    assert [m.content for m in found] == ["written before the split"]
    assert found[0].kind is MessageKind.CHAT
