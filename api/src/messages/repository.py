"""
Repository for Message entity using DynamoDB single table design.
"""

import base64
import json
import logging
from typing import Optional, Tuple

import boto3
from boto3.dynamodb.conditions import Key

from src.config import settings
from src.messages.models import Message

log = logging.getLogger(__name__)


class MessageRepository:
    """
    Repository for Message entity using DynamoDB single table design.

    Key Structure:
        pk: CONVERSATION#{conversation_id}  - Partition by conversation for efficient queries
        sk: MESSAGE#{timestamp}#{message_id}  - Chronological ordering within conversation

    Access Patterns:
        - save: PutItem (create)
        - find_by_conversation: Query by pk with sk prefix "MESSAGE#"
        - find_by_conversation_paginated: Query with pagination
    """

    def __init__(self):
        self.dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, message: Message) -> Message:
        """
        Save a message (always creates new, messages are immutable).
        """
        self.table.put_item(Item=message.to_dynamo_item())
        log.info(
            f"Saved message {message.message_id} for conversation {message.conversation_id}"
        )
        return message

    def find_by_conversation(self, conversation_id: str) -> list[Message]:
        """
        Find all messages for a specific conversation.

        Args:
            conversation_id: The unique conversation identifier

        Returns:
            List of messages sorted by created_at ascending (oldest first)
        """
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(f"CONVERSATION#{conversation_id}")
                & Key("sk").begins_with("MESSAGE#")
            )
        )

        items = response.get("Items", [])
        messages = [Message.from_dynamo_item(item) for item in items]

        # Sort by created_at ascending (oldest first) - sk is already ordered
        messages.sort(key=lambda m: m.created_at)

        log.info(f"Found {len(messages)} messages for conversation {conversation_id}")
        return messages

    def find_by_conversation_paginated(
        self, conversation_id: str, limit: int = 50, cursor: Optional[str] = None
    ) -> Tuple[list[Message], Optional[str], bool]:
        """
        Find messages for a conversation with pagination.

        Returns messages in chronological order (oldest first).

        Args:
            conversation_id: The unique conversation identifier
            limit: Maximum number of items to return
            cursor: Base64 encoded cursor for pagination

        Returns:
            Tuple of (messages, next_cursor, has_more)
        """
        query_params = {
            "KeyConditionExpression": (
                Key("pk").eq(f"CONVERSATION#{conversation_id}")
                & Key("sk").begins_with("MESSAGE#")
            ),
            "Limit": limit,
        }

        # Apply cursor if provided
        if cursor:
            try:
                cursor_data = json.loads(base64.b64decode(cursor).decode("utf-8"))
                query_params["ExclusiveStartKey"] = cursor_data
            except Exception:
                log.warning(f"Invalid cursor: {cursor}")

        response = self.table.query(**query_params)

        items = response.get("Items", [])
        messages = [Message.from_dynamo_item(item) for item in items]

        # Check for more items
        last_evaluated_key = response.get("LastEvaluatedKey")
        has_more = last_evaluated_key is not None

        # Create next cursor
        next_cursor = None
        if has_more and last_evaluated_key:
            next_cursor = base64.b64encode(
                json.dumps(last_evaluated_key).encode("utf-8")
            ).decode("utf-8")

        log.info(
            f"Found {len(messages)} messages for conversation {conversation_id} "
            f"(limit={limit}, has_more={has_more})"
        )

        return messages, next_cursor, has_more

    def find_by_conversation_newest_first(
        self, conversation_id: str, limit: int = 20, cursor: Optional[str] = None
    ) -> Tuple[list[Message], Optional[str], bool]:
        """
        Find messages for a conversation, newest first (for infinite scroll up).

        Returns messages in reverse chronological order (newest first).
        Use cursor to load older messages.

        Args:
            conversation_id: The unique conversation identifier
            limit: Maximum number of items to return
            cursor: Base64 encoded cursor for pagination (points to older messages)

        Returns:
            Tuple of (messages, next_cursor, has_more)
            - messages: List of messages, newest first
            - next_cursor: Cursor to fetch older messages
            - has_more: True if there are more (older) messages
        """
        query_params = {
            "KeyConditionExpression": (
                Key("pk").eq(f"CONVERSATION#{conversation_id}")
                & Key("sk").begins_with("MESSAGE#")
            ),
            "Limit": limit,
            "ScanIndexForward": False,  # Newest first
        }

        # Apply cursor if provided
        if cursor:
            try:
                cursor_data = json.loads(base64.b64decode(cursor).decode("utf-8"))
                query_params["ExclusiveStartKey"] = cursor_data
            except Exception:
                log.warning(f"Invalid cursor: {cursor}")

        response = self.table.query(**query_params)

        items = response.get("Items", [])
        messages = [Message.from_dynamo_item(item) for item in items]

        # Check for more items (older messages)
        last_evaluated_key = response.get("LastEvaluatedKey")
        has_more = last_evaluated_key is not None

        # Create next cursor (points to older messages)
        next_cursor = None
        if has_more and last_evaluated_key:
            next_cursor = base64.b64encode(
                json.dumps(last_evaluated_key).encode("utf-8")
            ).decode("utf-8")

        log.info(
            f"Found {len(messages)} messages (newest first) for conversation {conversation_id} "
            f"(limit={limit}, has_more={has_more})"
        )

        return messages, next_cursor, has_more

    def count_by_conversation(self, conversation_id: str) -> int:
        """
        Count messages in a conversation.

        Args:
            conversation_id: The unique conversation identifier

        Returns:
            Number of messages in the conversation
        """
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(f"CONVERSATION#{conversation_id}")
                & Key("sk").begins_with("MESSAGE#")
            ),
            Select="COUNT",
        )

        return response.get("Count", 0)

    def delete_by_conversation(self, conversation_id: str) -> int:
        """
        Delete all messages in a conversation.

        Args:
            conversation_id: The unique conversation identifier

        Returns:
            Number of messages deleted
        """
        messages = self.find_by_conversation(conversation_id)

        with self.table.batch_writer() as batch:
            for message in messages:
                batch.delete_item(Key={"pk": message.pk, "sk": message.sk})

        log.info(
            f"Deleted {len(messages)} messages for conversation {conversation_id}"
        )
        return len(messages)
