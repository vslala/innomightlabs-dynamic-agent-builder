"""
Tests for Messages module.
"""

import pytest
from datetime import datetime, timezone

from src.messages.models import Message, MessageResponse
from src.messages.repository import MessageRepository
from tests.mock_data import TEST_USER_EMAIL


@pytest.fixture
def message_repository(dynamodb_table):
    """Create MessageRepository with mocked DynamoDB."""
    return MessageRepository()


class TestMessageModel:
    """Tests for Message model."""

    def test_message_default_values(self):
        """Test that Message sets default values correctly."""
        message = Message(
            conversation_id="conv-123",
            role="user",
            content="Hello world",
        )

        assert message.message_id is not None
        assert message.conversation_id == "conv-123"
        assert message.role == "user"
        assert message.content == "Hello world"
        assert message.created_at is not None

    def test_message_pk_format(self):
        """Test that pk is formatted correctly."""
        message = Message(
            conversation_id="conv-123",
            role="user",
            content="Hello",
        )

        assert message.pk == "CONVERSATION#conv-123"

    def test_message_sk_format(self):
        """Test that sk is formatted correctly."""
        message = Message(
            conversation_id="conv-123",
            role="user",
            content="Hello",
        )

        # sk should be MESSAGE#{timestamp}#{message_id}
        assert message.sk.startswith("MESSAGE#")
        assert message.message_id in message.sk

    def test_message_to_dynamo_item(self):
        """Test DynamoDB item serialization."""
        message = Message(
            conversation_id="conv-123",
            role="user",
            content="Hello",
        )

        item = message.to_dynamo_item()

        assert item["pk"] == "CONVERSATION#conv-123"
        assert item["sk"].startswith("MESSAGE#")
        assert item["message_id"] == message.message_id
        assert item["conversation_id"] == "conv-123"
        assert item["role"] == "user"
        assert item["content"] == "Hello"
        assert "created_at" in item

    def test_message_from_dynamo_item(self):
        """Test DynamoDB item deserialization."""
        now = datetime.now(timezone.utc)
        item = {
            "pk": "CONVERSATION#conv-123",
            "sk": f"MESSAGE#{now.isoformat()}#msg-456",
            "message_id": "msg-456",
            "conversation_id": "conv-123",
            "role": "assistant",
            "content": "Hello there!",
            "created_at": now.isoformat(),
        }

        message = Message.from_dynamo_item(item)

        assert message.message_id == "msg-456"
        assert message.conversation_id == "conv-123"
        assert message.role == "assistant"
        assert message.content == "Hello there!"

    def test_message_to_response(self):
        """Test conversion to response model."""
        message = Message(
            conversation_id="conv-123",
            role="user",
            content="Hello",
        )

        response = message.to_response()

        assert isinstance(response, MessageResponse)
        assert response.message_id == message.message_id
        assert response.conversation_id == "conv-123"
        assert response.role == "user"
        assert response.content == "Hello"


class TestMessageRepository:
    """Tests for MessageRepository."""

    def test_save_creates_new_message(self, message_repository):
        """Test that save() creates a new message."""
        message = Message(
            conversation_id="conv-123",
            role="user",
            content="Hello world",
        )

        saved = message_repository.save(message)

        assert saved.message_id == message.message_id
        assert saved.conversation_id == "conv-123"
        assert saved.role == "user"
        assert saved.content == "Hello world"

    def test_find_by_conversation(self, message_repository):
        """Test that find_by_conversation() retrieves all messages."""
        # Create multiple messages
        message1 = Message(
            conversation_id="conv-123",
            role="user",
            content="Hello",
        )
        message2 = Message(
            conversation_id="conv-123",
            role="assistant",
            content="Hi there!",
        )
        message3 = Message(
            conversation_id="conv-123",
            role="user",
            content="How are you?",
        )

        message_repository.save(message1)
        message_repository.save(message2)
        message_repository.save(message3)

        messages = message_repository.find_by_conversation("conv-123")

        assert len(messages) == 3
        # Should be sorted by created_at ascending
        contents = [m.content for m in messages]
        assert "Hello" in contents
        assert "Hi there!" in contents
        assert "How are you?" in contents

    def test_find_by_conversation_returns_empty_for_no_messages(
        self, message_repository
    ):
        """Test that find_by_conversation() returns empty list when no messages exist."""
        messages = message_repository.find_by_conversation("non-existent-conv")

        assert messages == []

    def test_find_by_conversation_only_returns_matching_conversation(
        self, message_repository
    ):
        """Test that messages from other conversations are not returned."""
        message1 = Message(
            conversation_id="conv-123",
            role="user",
            content="Message for conv-123",
        )
        message2 = Message(
            conversation_id="conv-456",
            role="user",
            content="Message for conv-456",
        )

        message_repository.save(message1)
        message_repository.save(message2)

        messages = message_repository.find_by_conversation("conv-123")

        assert len(messages) == 1
        assert messages[0].content == "Message for conv-123"

    def test_find_by_conversation_paginated(self, message_repository):
        """Test paginated message retrieval."""
        # Create 5 messages
        for i in range(5):
            message = Message(
                conversation_id="conv-123",
                role="user",
                content=f"Message {i}",
            )
            message_repository.save(message)

        # Get first page
        messages, next_cursor, has_more = (
            message_repository.find_by_conversation_paginated(
                conversation_id="conv-123", limit=2
            )
        )

        assert len(messages) == 2
        assert next_cursor is not None
        assert has_more is True

        # Get second page
        messages2, next_cursor2, has_more2 = (
            message_repository.find_by_conversation_paginated(
                conversation_id="conv-123", limit=2, cursor=next_cursor
            )
        )

        assert len(messages2) == 2
        assert next_cursor2 is not None
        assert has_more2 is True

        # Get last page
        messages3, next_cursor3, has_more3 = (
            message_repository.find_by_conversation_paginated(
                conversation_id="conv-123", limit=2, cursor=next_cursor2
            )
        )

        assert len(messages3) == 1
        assert next_cursor3 is None
        assert has_more3 is False

    def test_count_by_conversation(self, message_repository):
        """Test count_by_conversation() returns correct count."""
        # Create messages for conv-123
        for i in range(3):
            message_repository.save(
                Message(
                    conversation_id="conv-123",
                    role="user",
                    content=f"Message {i}",
                )
            )

        # Create message for different conversation
        message_repository.save(
            Message(
                conversation_id="conv-456",
                role="user",
                content="Other message",
            )
        )

        count = message_repository.count_by_conversation("conv-123")

        assert count == 3

    def test_count_by_conversation_returns_zero_for_no_messages(
        self, message_repository
    ):
        """Test count_by_conversation() returns 0 when no messages exist."""
        count = message_repository.count_by_conversation("non-existent-conv")

        assert count == 0

    def test_delete_by_conversation(self, message_repository):
        """Test delete_by_conversation() removes all messages."""
        # Create messages
        for i in range(3):
            message_repository.save(
                Message(
                    conversation_id="conv-123",
                    role="user",
                    content=f"Message {i}",
                )
            )

        # Delete all messages
        deleted_count = message_repository.delete_by_conversation("conv-123")

        assert deleted_count == 3
        assert message_repository.count_by_conversation("conv-123") == 0

    def test_delete_by_conversation_does_not_affect_other_conversations(
        self, message_repository
    ):
        """Test delete_by_conversation() only deletes for specified conversation."""
        # Create messages for both conversations
        message_repository.save(
            Message(
                conversation_id="conv-123",
                role="user",
                content="Message for conv-123",
            )
        )
        message_repository.save(
            Message(
                conversation_id="conv-456",
                role="user",
                content="Message for conv-456",
            )
        )

        # Delete only conv-123
        message_repository.delete_by_conversation("conv-123")

        assert message_repository.count_by_conversation("conv-123") == 0
        assert message_repository.count_by_conversation("conv-456") == 1

    def test_messages_ordered_chronologically(self, message_repository):
        """Test that messages are returned in chronological order."""
        import time

        messages_data = [
            ("Hello", "user"),
            ("Hi there!", "assistant"),
            ("How are you?", "user"),
        ]

        for content, role in messages_data:
            message = Message(
                conversation_id="conv-123",
                role=role,
                content=content,
            )
            message_repository.save(message)
            time.sleep(0.01)  # Small delay to ensure different timestamps

        messages = message_repository.find_by_conversation("conv-123")

        # Should be in chronological order
        assert messages[0].content == "Hello"
        assert messages[1].content == "Hi there!"
        assert messages[2].content == "How are you?"
