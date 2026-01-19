"""
Repository for WidgetConversation entity using DynamoDB single table design.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import boto3
from boto3.dynamodb.conditions import Key

from src.config import settings
from src.widget.models import WidgetConversation

log = logging.getLogger(__name__)


class WidgetConversationRepository:
    """
    Repository for WidgetConversation entity.

    Key Structure:
        pk: Agent#{agent_id}#Widget
        sk: Conversation#{conversation_id}

    GSI2 (for visitor lookup):
        gsi2_pk: Visitor#{visitor_id}
        gsi2_sk: Agent#{agent_id}#Conversation#{conversation_id}

    Access Patterns:
        - save: PutItem (create or update)
        - find_by_id: GetItem by pk + sk
        - find_by_agent: Query by pk
        - find_by_visitor: Query GSI2 by gsi2_pk
        - find_by_visitor_and_agent: Query GSI2 with sk prefix
        - delete_by_id: DeleteItem by pk + sk
    """

    GSI2_NAME = "gsi2"

    def __init__(self) -> None:
        self.dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, conversation: WidgetConversation) -> WidgetConversation:
        """
        Save a widget conversation (create or update).

        If conversation exists, preserves created_at and updates updated_at.
        """
        existing = self.find_by_id(conversation.agent_id, conversation.conversation_id)

        if existing:
            conversation.created_at = existing.created_at
            conversation.updated_at = datetime.now(timezone.utc)

        self.table.put_item(Item=conversation.to_dynamo_item())
        log.info(
            f"Saved widget conversation {conversation.conversation_id} "
            f"for agent {conversation.agent_id}"
        )
        return conversation

    def find_by_id(
        self, agent_id: str, conversation_id: str
    ) -> Optional[WidgetConversation]:
        """
        Find a widget conversation by agent ID and conversation ID.

        Args:
            agent_id: The agent this conversation belongs to
            conversation_id: The unique conversation identifier

        Returns:
            WidgetConversation if found, None otherwise
        """
        response = self.table.get_item(
            Key={
                "pk": f"Agent#{agent_id}#Widget",
                "sk": f"Conversation#{conversation_id}",
            }
        )
        item = response.get("Item")
        if item:
            return WidgetConversation.from_dynamo_item(item)
        return None

    def find_by_agent(
        self,
        agent_id: str,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> tuple[list[WidgetConversation], Optional[str], bool]:
        """
        Find all widget conversations for an agent.

        Returns newest first with cursor-based pagination.

        Args:
            agent_id: The agent ID
            limit: Maximum number of conversations to return
            cursor: Pagination cursor (conversation_id to start after)

        Returns:
            Tuple of (conversations, next_cursor, has_more)
        """
        query_kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(f"Agent#{agent_id}#Widget"),
            "ScanIndexForward": False,  # Newest first
            "Limit": limit + 1,  # Fetch one extra to check has_more
        }

        if cursor:
            query_kwargs["ExclusiveStartKey"] = {
                "pk": f"Agent#{agent_id}#Widget",
                "sk": f"Conversation#{cursor}",
            }

        response = self.table.query(**query_kwargs)
        items = response.get("Items", [])

        has_more = len(items) > limit
        if has_more:
            items = items[:limit]

        conversations = [WidgetConversation.from_dynamo_item(item) for item in items]
        next_cursor = conversations[-1].conversation_id if has_more and conversations else None

        return conversations, next_cursor, has_more

    def find_by_visitor(
        self,
        visitor_id: str,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> tuple[list[WidgetConversation], Optional[str], bool]:
        """
        Find all widget conversations for a visitor across all agents.

        Uses GSI2 for efficient lookup.

        Args:
            visitor_id: The visitor's ID (from OAuth)
            limit: Maximum number of conversations to return
            cursor: Pagination cursor

        Returns:
            Tuple of (conversations, next_cursor, has_more)
        """
        query_kwargs: dict[str, Any] = {
            "IndexName": self.GSI2_NAME,
            "KeyConditionExpression": Key("gsi2_pk").eq(f"Visitor#{visitor_id}"),
            "ScanIndexForward": False,
            "Limit": limit + 1,
        }

        if cursor:
            # Need to decode cursor to get the full key
            query_kwargs["ExclusiveStartKey"] = {
                "gsi2_pk": f"Visitor#{visitor_id}",
                "gsi2_sk": cursor,
            }

        response = self.table.query(**query_kwargs)
        items = response.get("Items", [])

        has_more = len(items) > limit
        if has_more:
            items = items[:limit]

        conversations = [WidgetConversation.from_dynamo_item(item) for item in items]
        next_cursor = conversations[-1].gsi2_sk if has_more and conversations else None

        return conversations, next_cursor, has_more

    def find_by_visitor_and_agent(
        self,
        visitor_id: str,
        agent_id: str,
    ) -> list[WidgetConversation]:
        """
        Find all conversations for a visitor with a specific agent.

        Uses GSI2 with sk prefix filter.

        Args:
            visitor_id: The visitor's ID
            agent_id: The agent ID

        Returns:
            List of conversations
        """
        response = self.table.query(
            IndexName=self.GSI2_NAME,
            KeyConditionExpression=(
                Key("gsi2_pk").eq(f"Visitor#{visitor_id}") &
                Key("gsi2_sk").begins_with(f"Agent#{agent_id}#")
            ),
        )

        items = response.get("Items", [])
        return [WidgetConversation.from_dynamo_item(item) for item in items]

    def delete_by_id(self, agent_id: str, conversation_id: str) -> bool:
        """
        Delete a widget conversation.

        Args:
            agent_id: The agent ID
            conversation_id: The conversation ID

        Returns:
            True if deleted successfully
        """
        try:
            self.table.delete_item(
                Key={
                    "pk": f"Agent#{agent_id}#Widget",
                    "sk": f"Conversation#{conversation_id}",
                }
            )
            log.info(f"Deleted widget conversation {conversation_id}")
            return True
        except Exception as e:
            log.error(f"Failed to delete widget conversation: {e}", exc_info=True)
            return False

    def increment_message_count(self, agent_id: str, conversation_id: str) -> None:
        """
        Increment the message count for a conversation.

        Args:
            agent_id: The agent ID
            conversation_id: The conversation ID
        """
        try:
            self.table.update_item(
                Key={
                    "pk": f"Agent#{agent_id}#Widget",
                    "sk": f"Conversation#{conversation_id}",
                },
                UpdateExpression="SET message_count = message_count + :inc, updated_at = :now",
                ExpressionAttributeValues={
                    ":inc": 1,
                    ":now": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as e:
            log.error(f"Failed to increment message count: {e}", exc_info=True)
