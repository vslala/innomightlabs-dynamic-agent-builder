from datetime import datetime, timedelta, timezone


from src.messages.models import Message
from src.messages.repositories.dynamodb import DynamoDBMessageRepository
from src.messages.repositories.in_memory import InMemoryMessageRepository


WATERMARK = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
CONVERSATION_ID = "conversation-1"


def message(message_id: str, created_at: datetime) -> Message:
    return Message(
        message_id=message_id,
        conversation_id=CONVERSATION_ID,
        role="user",
        content="hello",
        created_at=created_at,
    )


def test_in_memory_has_messages_after_excludes_watermark_and_includes_later_message():
    repository = InMemoryMessageRepository()
    repository.save(message("at-watermark", WATERMARK))

    assert repository.has_messages_after(CONVERSATION_ID, WATERMARK) is False

    repository.save(message("after-watermark", WATERMARK + timedelta(microseconds=1)))

    assert repository.has_messages_after(CONVERSATION_ID, WATERMARK) is True
    assert repository.has_messages_after("empty-conversation", WATERMARK) is False



def test_dynamodb_has_messages_after_matches_in_memory_strict_boundary(dynamodb_table):
    dynamo_repository = DynamoDBMessageRepository()
    in_memory_repository = InMemoryMessageRepository()
    messages = [
        message("at-watermark", WATERMARK),
        message("after-watermark", WATERMARK + timedelta(microseconds=1)),
    ]
    for item in messages:
        dynamo_repository.save(item)
        in_memory_repository.save(item)

    assert dynamo_repository.has_messages_after(CONVERSATION_ID, WATERMARK) is True
    assert dynamo_repository.has_messages_after("empty-conversation", WATERMARK) is False

    exact_only = message("exact-only", WATERMARK)
    dynamo_repository.save(exact_only.model_copy(update={"conversation_id": "exact-only"}))
    in_memory_repository.save(exact_only.model_copy(update={"conversation_id": "exact-only"}))

    assert dynamo_repository.has_messages_after("exact-only", WATERMARK) is False
    assert dynamo_repository.has_messages_after(
        "exact-only", WATERMARK
    ) == in_memory_repository.has_messages_after("exact-only", WATERMARK)
