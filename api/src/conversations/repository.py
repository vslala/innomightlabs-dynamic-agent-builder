"""
Repository for Conversation entity using DynamoDB single table design.
"""

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from ..db import get_dynamodb_resource
from boto3.dynamodb.conditions import Key

from src.config import settings
from src.conversations.models import Conversation

log = logging.getLogger(__name__)


class ConversationRepository:
    """
    Repository for Conversation entity using DynamoDB single table design.

    Key Structure:
        pk: USER#{created_by_email}      - Partition by user for efficient queries
        sk: CONVERSATION#{conversation_id}  - Unique conversation identifier

    Access Patterns:
        - save: PutItem (create or update)
        - find_by_id: GetItem by pk + sk
        - find_all_by_user: Query by pk with sk prefix "CONVERSATION#"
        - find_all_by_user_paginated: Query with pagination, reverse chronological
        - delete_by_id: DeleteItem by pk + sk
    """

    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, conversation: Conversation) -> Conversation:
        """
        Save a conversation (create or update).

        If conversation_id exists, updates the existing record.
        Otherwise, creates a new record.
        """
        existing = self.find_by_id(conversation.conversation_id, conversation.created_by)

        if existing:
            # Update: preserve created_at, update updated_at
            conversation.created_at = existing.created_at
            conversation.updated_at = datetime.now(timezone.utc)

        self.table.put_item(Item=conversation.to_dynamo_item())
        log.info(f"Saved conversation {conversation.conversation_id} for user {conversation.created_by}")
        return conversation

    def find_by_id(self, conversation_id: str, created_by: str) -> Optional[Conversation]:
        """
        Find a conversation by ID and creator email.

        Args:
            conversation_id: The unique conversation identifier
            created_by: The email of the user who created the conversation

        Returns:
            Conversation if found, None otherwise
        """
        response = self.table.get_item(
            Key={
                "pk": f"USER#{created_by}",
                "sk": f"CONVERSATION#{conversation_id}",
            }
        )
        item = response.get("Item")
        if item:
            return Conversation.from_dynamo_item(item)
        return None

    def find_all_by_user(self, created_by: str) -> list[Conversation]:
        """
        Find all conversations for a specific user.

        Args:
            created_by: The email of the user

        Returns:
            List of conversations for the user, sorted by created_at desc
        """
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(f"USER#{created_by}") & Key("sk").begins_with("CONVERSATION#")
            )
        )

        items = response.get("Items", [])
        conversations = [Conversation.from_dynamo_item(item) for item in items]

        # Sort by created_at descending (most recent first)
        conversations.sort(key=lambda c: c.created_at, reverse=True)

        log.info(f"Found {len(conversations)} conversations for user {created_by}")
        return conversations

    def find_all_by_user_paginated(
        self, created_by: str, limit: int = 10, cursor: Optional[str] = None
    ) -> Tuple[list[Conversation], Optional[str], bool]:
        """
        Find conversations for a user with pagination.

        Returns conversations in reverse chronological order (most recent first).

        Args:
            created_by: The email of the user
            limit: Maximum number of items to return
            cursor: Base64 encoded cursor for pagination (offset index)

        Returns:
            Tuple of (conversations, next_cursor, has_more)
        """
        # Query all conversations for user
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(f"USER#{created_by}") & Key("sk").begins_with("CONVERSATION#")
            )
        )

        items = response.get("Items", [])
        conversations = [Conversation.from_dynamo_item(item) for item in items]

        # Sort by created_at descending (most recent first)
        conversations.sort(key=lambda c: c.created_at, reverse=True)

        # Apply cursor-based pagination (cursor is the offset index)
        offset = 0
        if cursor:
            try:
                cursor_data = json.loads(base64.b64decode(cursor).decode("utf-8"))
                offset = cursor_data.get("offset", 0)
            except Exception:
                log.warning(f"Invalid cursor: {cursor}")
                offset = 0

        # Get paginated slice
        paginated = conversations[offset : offset + limit]
        has_more = len(conversations) > offset + limit

        # Create next cursor
        next_cursor = None
        if has_more:
            next_offset = offset + limit
            cursor_data = {"offset": next_offset}
            next_cursor = base64.b64encode(json.dumps(cursor_data).encode("utf-8")).decode("utf-8")

        log.info(
            f"Found {len(paginated)} conversations for user {created_by} "
            f"(offset={offset}, limit={limit}, has_more={has_more})"
        )

        return paginated, next_cursor, has_more

    def delete_by_id(self, conversation_id: str, created_by: str) -> bool:
        """
        Delete a conversation by ID.

        Args:
            conversation_id: The unique conversation identifier
            created_by: The email of the user who created the conversation

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            self.table.delete_item(
                Key={
                    "pk": f"USER#{created_by}",
                    "sk": f"CONVERSATION#{conversation_id}",
                }
            )
            log.info(f"Deleted conversation {conversation_id} for user {created_by}")
            return True
        except Exception as e:
            log.error(f"Failed to delete conversation {conversation_id}: {e}", exc_info=True)
            return False

    def exists(self, conversation_id: str, created_by: str) -> bool:
        """Check if a conversation exists."""
        return self.find_by_id(conversation_id, created_by) is not None
