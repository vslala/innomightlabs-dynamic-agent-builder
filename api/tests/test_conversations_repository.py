"""
Tests for ConversationRepository.
"""

import pytest

from src.conversations.models import Conversation
from tests.mock_data import (
    TEST_USER_EMAIL,
    TEST_USER_EMAIL_2,
    CONVERSATION_CREATE_REQUEST,
    CONVERSATION_CREATE_REQUEST_2,
)


class TestConversationRepository:
    """Tests for ConversationRepository."""

    def test_save_creates_new_conversation(self, conversation_repository):
        """Test that save() creates a new conversation."""
        conversation = Conversation(
            title=CONVERSATION_CREATE_REQUEST["title"],
            description=CONVERSATION_CREATE_REQUEST["description"],
            agent_id=CONVERSATION_CREATE_REQUEST["agent_id"],
            created_by=TEST_USER_EMAIL,
        )

        saved = conversation_repository.save(conversation)

        assert saved.conversation_id == conversation.conversation_id
        assert saved.title == CONVERSATION_CREATE_REQUEST["title"]
        assert saved.description == CONVERSATION_CREATE_REQUEST["description"]
        assert saved.agent_id == CONVERSATION_CREATE_REQUEST["agent_id"]
        assert saved.created_by == TEST_USER_EMAIL

    def test_find_by_id(self, conversation_repository):
        """Test that find_by_id() retrieves the correct conversation."""
        conversation = Conversation(
            title=CONVERSATION_CREATE_REQUEST["title"],
            description=CONVERSATION_CREATE_REQUEST["description"],
            agent_id=CONVERSATION_CREATE_REQUEST["agent_id"],
            created_by=TEST_USER_EMAIL,
        )
        conversation_repository.save(conversation)

        found = conversation_repository.find_by_id(
            conversation.conversation_id, TEST_USER_EMAIL
        )

        assert found is not None
        assert found.conversation_id == conversation.conversation_id
        assert found.title == conversation.title

    def test_find_by_id_returns_none_for_different_user(self, conversation_repository):
        """Test that find_by_id() returns None for a different user."""
        conversation = Conversation(
            title=CONVERSATION_CREATE_REQUEST["title"],
            description=CONVERSATION_CREATE_REQUEST["description"],
            agent_id=CONVERSATION_CREATE_REQUEST["agent_id"],
            created_by=TEST_USER_EMAIL,
        )
        conversation_repository.save(conversation)

        found = conversation_repository.find_by_id(
            conversation.conversation_id, TEST_USER_EMAIL_2
        )

        assert found is None

    def test_find_all_by_user(self, conversation_repository):
        """Test that find_all_by_user() retrieves all conversations for a user."""
        conversation1 = Conversation(
            title=CONVERSATION_CREATE_REQUEST["title"],
            description=CONVERSATION_CREATE_REQUEST["description"],
            agent_id=CONVERSATION_CREATE_REQUEST["agent_id"],
            created_by=TEST_USER_EMAIL,
        )
        conversation2 = Conversation(
            title=CONVERSATION_CREATE_REQUEST_2["title"],
            description=CONVERSATION_CREATE_REQUEST_2["description"],
            agent_id=CONVERSATION_CREATE_REQUEST_2["agent_id"],
            created_by=TEST_USER_EMAIL,
        )
        conversation_repository.save(conversation1)
        conversation_repository.save(conversation2)

        conversations = conversation_repository.find_all_by_user(TEST_USER_EMAIL)

        assert len(conversations) == 2
        titles = {c.title for c in conversations}
        assert CONVERSATION_CREATE_REQUEST["title"] in titles
        assert CONVERSATION_CREATE_REQUEST_2["title"] in titles

    def test_find_all_by_user_returns_empty_for_no_conversations(
        self, conversation_repository
    ):
        """Test that find_all_by_user() returns empty list when no conversations exist."""
        conversations = conversation_repository.find_all_by_user(TEST_USER_EMAIL)

        assert conversations == []

    def test_find_all_by_user_paginated(self, conversation_repository):
        """Test paginated conversation retrieval."""
        # Create 5 conversations
        for i in range(5):
            conversation = Conversation(
                title=f"Conversation {i}",
                description=f"Description {i}",
                agent_id="test-agent-id",
                created_by=TEST_USER_EMAIL,
            )
            conversation_repository.save(conversation)

        # Get first page
        conversations, next_cursor, has_more = (
            conversation_repository.find_all_by_user_paginated(
                created_by=TEST_USER_EMAIL, limit=2
            )
        )

        assert len(conversations) == 2
        assert next_cursor is not None
        assert has_more is True

        # Get second page
        conversations2, next_cursor2, has_more2 = (
            conversation_repository.find_all_by_user_paginated(
                created_by=TEST_USER_EMAIL, limit=2, cursor=next_cursor
            )
        )

        assert len(conversations2) == 2
        assert next_cursor2 is not None
        assert has_more2 is True

        # Get last page
        conversations3, next_cursor3, has_more3 = (
            conversation_repository.find_all_by_user_paginated(
                created_by=TEST_USER_EMAIL, limit=2, cursor=next_cursor2
            )
        )

        assert len(conversations3) == 1
        assert next_cursor3 is None
        assert has_more3 is False

    def test_delete_by_id(self, conversation_repository):
        """Test that delete_by_id() removes the conversation."""
        conversation = Conversation(
            title=CONVERSATION_CREATE_REQUEST["title"],
            description=CONVERSATION_CREATE_REQUEST["description"],
            agent_id=CONVERSATION_CREATE_REQUEST["agent_id"],
            created_by=TEST_USER_EMAIL,
        )
        conversation_repository.save(conversation)

        result = conversation_repository.delete_by_id(
            conversation.conversation_id, TEST_USER_EMAIL
        )

        assert result is True
        assert (
            conversation_repository.find_by_id(
                conversation.conversation_id, TEST_USER_EMAIL
            )
            is None
        )

    def test_save_updates_existing_conversation(self, conversation_repository):
        """Test that save() updates an existing conversation."""
        conversation = Conversation(
            title=CONVERSATION_CREATE_REQUEST["title"],
            description=CONVERSATION_CREATE_REQUEST["description"],
            agent_id=CONVERSATION_CREATE_REQUEST["agent_id"],
            created_by=TEST_USER_EMAIL,
        )
        saved = conversation_repository.save(conversation)
        original_created_at = saved.created_at

        # Update the conversation
        saved.title = "Updated Title"
        saved.description = "Updated description"
        updated = conversation_repository.save(saved)

        assert updated.title == "Updated Title"
        assert updated.description == "Updated description"
        assert updated.created_at == original_created_at
        assert updated.updated_at is not None

    def test_exists(self, conversation_repository):
        """Test exists() method."""
        conversation = Conversation(
            title=CONVERSATION_CREATE_REQUEST["title"],
            description=CONVERSATION_CREATE_REQUEST["description"],
            agent_id=CONVERSATION_CREATE_REQUEST["agent_id"],
            created_by=TEST_USER_EMAIL,
        )
        conversation_repository.save(conversation)

        assert (
            conversation_repository.exists(
                conversation.conversation_id, TEST_USER_EMAIL
            )
            is True
        )
        assert (
            conversation_repository.exists("non-existent-id", TEST_USER_EMAIL) is False
        )
