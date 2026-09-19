"""
DynamoDB-backed repository for Message entities.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime
from typing import Any, Optional, Tuple

from boto3.dynamodb.conditions import Key

from src.config import settings
from src.db import get_dynamodb_resource
from src.messages.models import (
    AUDIT_SORT_KEY_PREFIX,
    CHAT_SORT_KEY_PREFIX,
    Message,
)

log = logging.getLogger(__name__)

Page = Tuple[list[Message], Optional[str], bool]


class DynamoDBMessageRepository:
    """
    Repository for Message entity using DynamoDB single table design.

    Key Structure:
        pk: CONVERSATION#{conversation_id}
        sk: MESSAGE#{timestamp}#{message_id}   chat messages
            AUDIT#{timestamp}#{message_id}     tool-call audit rows

    The two prefixes keep audit rows -- written on every tool call, capped at
    MAX_TOOL_RESULT_CHARS each -- out of every query on the conversation path.
    """

    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, message: Message) -> Message:
        self.table.put_item(Item=message.to_dynamo_item())
        log.info(
            f"Saved message {message.message_id} for conversation {message.conversation_id}"
        )
        return message

    def find_by_conversation(self, conversation_id: str) -> list[Message]:
        """Every chat message in the conversation, oldest first.

        Follows LastEvaluatedKey: a single query returns at most 1MB, and
        silently dropping the remainder here fed the LLM a truncated
        conversation -- see api/docs/LLD-agent-runtime-refactor.md (P0.1).
        """
        messages = self._query_all(conversation_id, CHAT_SORT_KEY_PREFIX)
        messages.sort(key=lambda m: m.created_at)

        log.info(f"Found {len(messages)} messages for conversation {conversation_id}")
        return messages

    def has_messages_after(self, conversation_id: str, after: datetime) -> bool:
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(self._pk(conversation_id))
                # The stored sort key includes `#{message_id}` after the timestamp.
                # `￿` excludes every message at the exact watermark timestamp.
                & Key("sk").gt(f"{CHAT_SORT_KEY_PREFIX}{after.isoformat()}￿")
            ),
            Limit=1,
            ProjectionExpression="sk",
        )
        return bool(response.get("Items"))

    def find_by_conversation_paginated(
        self, conversation_id: str, limit: int = 50, cursor: Optional[str] = None
    ) -> Page:
        return self._query_page(
            conversation_id, CHAT_SORT_KEY_PREFIX, limit=limit, cursor=cursor
        )

    def find_by_conversation_newest_first(
        self, conversation_id: str, limit: int = 20, cursor: Optional[str] = None
    ) -> Page:
        return self._query_page(
            conversation_id,
            CHAT_SORT_KEY_PREFIX,
            limit=limit,
            cursor=cursor,
            newest_first=True,
        )

    def find_audit_by_conversation(
        self, conversation_id: str, limit: int = 20, cursor: Optional[str] = None
    ) -> Page:
        """The tool-call audit trail, newest first. Inspection only."""
        return self._query_page(
            conversation_id,
            AUDIT_SORT_KEY_PREFIX,
            limit=limit,
            cursor=cursor,
            newest_first=True,
        )

    def count_by_conversation(self, conversation_id: str) -> int:
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(self._pk(conversation_id))
                & Key("sk").begins_with(CHAT_SORT_KEY_PREFIX)
            ),
            Select="COUNT",
        )

        return int(response.get("Count", 0))

    def delete_by_conversation(self, conversation_id: str) -> int:
        """Delete every row in the conversation partition, audit rows included."""
        rows = [
            *self._query_all(conversation_id, CHAT_SORT_KEY_PREFIX),
            *self._query_all(conversation_id, AUDIT_SORT_KEY_PREFIX),
        ]

        with self.table.batch_writer() as batch:
            for message in rows:
                batch.delete_item(Key={"pk": message.pk, "sk": message.sk})

        log.info(f"Deleted {len(rows)} messages for conversation {conversation_id}")
        return len(rows)

    @staticmethod
    def _pk(conversation_id: str) -> str:
        return f"CONVERSATION#{conversation_id}"

    def _query_all(self, conversation_id: str, prefix: str) -> list[Message]:
        condition = Key("pk").eq(self._pk(conversation_id)) & Key("sk").begins_with(prefix)
        params: dict[str, Any] = {"KeyConditionExpression": condition}
        messages: list[Message] = []

        while True:
            response = self.table.query(**params)
            messages.extend(
                Message.from_dynamo_item(item) for item in response.get("Items", [])
            )
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                return messages
            params["ExclusiveStartKey"] = last_key

    def _query_page(
        self,
        conversation_id: str,
        prefix: str,
        *,
        limit: int,
        cursor: Optional[str],
        newest_first: bool = False,
    ) -> Page:
        params: dict[str, Any] = {
            "KeyConditionExpression": (
                Key("pk").eq(self._pk(conversation_id)) & Key("sk").begins_with(prefix)
            ),
            "Limit": limit,
        }
        if newest_first:
            params["ScanIndexForward"] = False

        start_key = _decode_cursor(cursor)
        if start_key:
            params["ExclusiveStartKey"] = start_key

        response = self.table.query(**params)
        messages = [Message.from_dynamo_item(item) for item in response.get("Items", [])]

        last_key = response.get("LastEvaluatedKey")
        log.info(
            f"Found {len(messages)} messages for conversation {conversation_id} "
            f"(prefix={prefix}, limit={limit}, has_more={last_key is not None})"
        )
        return messages, _encode_cursor(last_key), last_key is not None


def _decode_cursor(cursor: Optional[str]) -> Optional[dict[str, Any]]:
    if not cursor:
        return None
    try:
        decoded = json.loads(base64.b64decode(cursor).decode("utf-8"))
    except Exception:
        log.warning(f"Invalid cursor: {cursor}")
        return None
    if not isinstance(decoded, dict):
        log.warning(f"Invalid cursor: {cursor}")
        return None
    return decoded


def _encode_cursor(last_key: Optional[dict[str, Any]]) -> Optional[str]:
    if not last_key:
        return None
    return base64.b64encode(json.dumps(last_key).encode("utf-8")).decode("utf-8")
