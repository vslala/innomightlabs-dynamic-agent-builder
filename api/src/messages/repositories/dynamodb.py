"""
DynamoDB-backed repository for Message entities.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Optional, Tuple

from boto3.dynamodb.conditions import Key

from src.config import settings
from src.db import get_dynamodb_resource
from src.messages.models import Message

log = logging.getLogger(__name__)


class DynamoDBMessageRepository:
    """
    Repository for Message entity using DynamoDB single table design.

    Key Structure:
        pk: CONVERSATION#{conversation_id}
        sk: MESSAGE#{timestamp}#{message_id}
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
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(f"CONVERSATION#{conversation_id}")
                & Key("sk").begins_with("MESSAGE#")
            )
        )

        items = response.get("Items", [])
        messages = [Message.from_dynamo_item(item) for item in items]
        messages.sort(key=lambda m: m.created_at)

        log.info(f"Found {len(messages)} messages for conversation {conversation_id}")
        return messages

    def find_by_conversation_paginated(
        self, conversation_id: str, limit: int = 50, cursor: Optional[str] = None
    ) -> Tuple[list[Message], Optional[str], bool]:
        query_params = {
            "KeyConditionExpression": (
                Key("pk").eq(f"CONVERSATION#{conversation_id}")
                & Key("sk").begins_with("MESSAGE#")
            ),
            "Limit": limit,
        }

        if cursor:
            try:
                cursor_data = json.loads(base64.b64decode(cursor).decode("utf-8"))
                query_params["ExclusiveStartKey"] = cursor_data
            except Exception:
                log.warning(f"Invalid cursor: {cursor}")

        response = self.table.query(**query_params)
        items = response.get("Items", [])
        messages = [Message.from_dynamo_item(item) for item in items]

        last_evaluated_key = response.get("LastEvaluatedKey")
        has_more = last_evaluated_key is not None
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
        query_params = {
            "KeyConditionExpression": (
                Key("pk").eq(f"CONVERSATION#{conversation_id}")
                & Key("sk").begins_with("MESSAGE#")
            ),
            "Limit": limit,
            "ScanIndexForward": False,
        }

        if cursor:
            try:
                cursor_data = json.loads(base64.b64decode(cursor).decode("utf-8"))
                query_params["ExclusiveStartKey"] = cursor_data
            except Exception:
                log.warning(f"Invalid cursor: {cursor}")

        response = self.table.query(**query_params)
        items = response.get("Items", [])
        messages = [Message.from_dynamo_item(item) for item in items]

        last_evaluated_key = response.get("LastEvaluatedKey")
        has_more = last_evaluated_key is not None
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
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(f"CONVERSATION#{conversation_id}")
                & Key("sk").begins_with("MESSAGE#")
            ),
            Select="COUNT",
        )

        return int(response.get("Count", 0))

    def delete_by_conversation(self, conversation_id: str) -> int:
        messages = self.find_by_conversation(conversation_id)

        with self.table.batch_writer() as batch:
            for message in messages:
                batch.delete_item(Key={"pk": message.pk, "sk": message.sk})

        log.info(
            f"Deleted {len(messages)} messages for conversation {conversation_id}"
        )
        return len(messages)
