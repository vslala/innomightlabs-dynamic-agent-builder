"""
Repository for Conversation entity using DynamoDB single table design.
"""

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Callable, Optional, Tuple

from ..db import get_dynamodb_resource
from boto3.dynamodb.conditions import Key

from src.config import settings
from src.conversations.models import ApiConversation, AutomationConversation, Conversation
from src.common.pagination import InvalidCursor

log = logging.getLogger(__name__)


class ConversationRepository:
    """
    Repository for Conversation entity using DynamoDB single table design.

    Key Structure:
        pk: Account#{account_id}#Member#{user_id}  - The partition of the member who started it
        sk: CONVERSATION#{conversation_id}         - Unique conversation identifier

        gsi2: Conversation#{conversation_id} / Conversation

    Requests name the partition (`Owner.member_pk`, `Agent.owner_partition` or
    `ApiConversation.partition_for(...)`), so a caller only reaches the
    conversations of the member, or key, they act as. Conversation ids are
    global, so work running inside a turn (skill actions, schedules it set up,
    image generation) finds the conversation by id alone with `get`.

    Access Patterns:
        - save: PutItem (create or update)
        - update_context: UpdateItem of `context` only
        - find_by_id: GetItem by pk + sk
        - find_all_by_user: Query by pk with sk prefix "CONVERSATION#"
        - find_all_by_user_paginated: Query with pagination, reverse chronological
        - delete_by_id: DeleteItem by pk + sk
    """

    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def _from_dynamo_item(self, item: dict) -> Conversation:
        """Hydrate the concrete conversation type represented by a DynamoDB item."""
        if (
            item.get("conversation_type") == "automation"
            or item.get("entity_type") == "AutomationConversation"
        ):
            return AutomationConversation.from_dynamo_item(item)

        if item.get("entity_type") == "ApiConversation":
            return ApiConversation.from_dynamo_item(item)

        return Conversation.from_dynamo_item(item)

    def save(self, conversation: Conversation) -> Conversation:
        """
        Save a conversation (create or update).

        If conversation_id exists, updates the existing record.
        Otherwise, creates a new record.
        """
        existing = self.find_by_id(conversation.conversation_id, conversation.pk)

        if existing:
            # Update: preserve created_at, update updated_at
            conversation.created_at = existing.created_at
            conversation.updated_at = datetime.now(timezone.utc)

        self.table.put_item(Item=conversation.to_dynamo_item())
        log.info(f"Saved conversation {conversation.conversation_id} in {conversation.pk}")
        return conversation

    def touch(self, conversation: Conversation) -> None:
        """Bump `updated_at` only, so the conversation sorts to the top of the list.

        `save()` would work, but it costs a read plus a full-item write and
        would clobber any field changed since this Conversation was loaded --
        renaming a conversation mid-turn used to be undone when the turn ended.
        """
        updated_at = datetime.now(timezone.utc)
        self.table.update_item(
            Key={"pk": conversation.pk, "sk": conversation.sk},
            UpdateExpression="SET updated_at = :updated_at",
            ExpressionAttributeValues={":updated_at": updated_at.isoformat()},
        )
        conversation.updated_at = updated_at

    def update_context(self, conversation: Conversation, context: str) -> None:
        """Set `context` alone, leaving every other field as it is stored."""
        updated_at = datetime.now(timezone.utc)
        self.table.update_item(
            Key={"pk": conversation.pk, "sk": conversation.sk},
            UpdateExpression="SET #context = :context, updated_at = :updated_at",
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeNames={"#context": "context"},
            ExpressionAttributeValues={":context": context, ":updated_at": updated_at.isoformat()},
        )
        conversation.context = context
        conversation.updated_at = updated_at

    def get(self, conversation_id: str) -> Optional[Conversation]:
        """The conversation with this id, whoever's it is: for work already running inside it, never for a
        request naming an id. The index is eventually consistent, so a just-created one may not show yet."""
        response = self.table.query(
            IndexName="gsi2",
            KeyConditionExpression=(
                Key("gsi2_pk").eq(f"Conversation#{conversation_id}") & Key("gsi2_sk").eq("Conversation")
            ),
        )
        items = response.get("Items", [])
        return self._from_dynamo_item(items[0]) if items else None

    def find_by_id(self, conversation_id: str, partition: str) -> Optional[Conversation]:
        """The conversation with this id in this member's partition, or None."""
        response = self.table.get_item(Key={"pk": partition, "sk": f"CONVERSATION#{conversation_id}"})
        item = response.get("Item")
        if item:
            return self._from_dynamo_item(item)
        return None

    def _query_all(self, partition: str) -> list[dict]:
        """Every conversation item in the member's partition, following DynamoDB's 1 MB pages."""
        query = {
            "KeyConditionExpression": Key("pk").eq(partition) & Key("sk").begins_with("CONVERSATION#")
        }
        items: list[dict] = []
        while True:
            response = self.table.query(**query)
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                return items
            query["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    def find_all_by_user(self, partition: str) -> list[Conversation]:
        """Every conversation in the member's partition, most recently active first."""
        conversations = [self._from_dynamo_item(item) for item in self._query_all(partition)]

        # Sort by last activity descending (most recently updated/created first)
        conversations.sort(key=lambda c: c.updated_at or c.created_at, reverse=True)

        log.info(f"Found {len(conversations)} conversations in {partition}")
        return conversations

    def find_all_by_user_paginated(
        self,
        partition: str,
        limit: int = 10,
        cursor: Optional[str] = None,
        keep: Optional[Callable[[Conversation], bool]] = None,
    ) -> Tuple[list[Conversation], Optional[str], bool]:
        """
        Find conversations for a user with pagination.

        Returns conversations ordered by last activity (most recently updated or
        created first).

        Args:
            partition: The member's partition
            limit: Maximum number of items to return
            cursor: Base64 encoded cursor for pagination (offset index)
            keep: Which conversations to list. Applied before paging, so every page is full.

        Returns:
            Tuple of (conversations, next_cursor, has_more)
        """
        conversations = [self._from_dynamo_item(item) for item in self._query_all(partition)]
        if keep is not None:
            conversations = [conversation for conversation in conversations if keep(conversation)]

        # Sort by last activity descending (most recently updated/created first)
        conversations.sort(key=lambda c: c.updated_at or c.created_at, reverse=True)

        # Apply cursor-based pagination (cursor is the offset index)
        offset = _decode_offset(cursor)

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
            f"Found {len(paginated)} conversations in {partition} "
            f"(offset={offset}, limit={limit}, has_more={has_more})"
        )

        return paginated, next_cursor, has_more

    def delete_by_id(self, conversation_id: str, partition: str) -> bool:
        """Delete the conversation with this id in this member's partition. False if the delete failed."""
        try:
            self.table.delete_item(Key={"pk": partition, "sk": f"CONVERSATION#{conversation_id}"})
            log.info(f"Deleted conversation {conversation_id} in {partition}")
            return True
        except Exception as e:
            log.error(f"Failed to delete conversation {conversation_id}: {e}", exc_info=True)
            return False

    def exists(self, conversation_id: str, partition: str) -> bool:
        """Check if a conversation exists."""
        return self.find_by_id(conversation_id, partition) is not None


def _decode_offset(cursor: Optional[str]) -> int:
    """This listing pages by offset; its cursor is {"offset": n}."""
    if not cursor:
        return 0
    try:
        offset = json.loads(base64.b64decode(cursor, validate=True).decode("utf-8")).get("offset")
    except (ValueError, UnicodeDecodeError, AttributeError) as exc:
        raise InvalidCursor("Invalid pagination cursor") from exc
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise InvalidCursor("Invalid pagination cursor")
    return offset
