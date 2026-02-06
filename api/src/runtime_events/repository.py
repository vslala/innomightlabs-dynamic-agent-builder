"""DynamoDB repository for RuntimeEvent log."""

from __future__ import annotations

import base64
import json
import logging
from typing import Optional, Tuple

from boto3.dynamodb.conditions import Key

from src.config import settings
from src.db import get_dynamodb_resource

from .models import RuntimeEvent, RuntimeEventPage

log = logging.getLogger(__name__)


def _encode_cursor(sk: str) -> str:
    return base64.urlsafe_b64encode(json.dumps({"sk": sk}).encode()).decode()


def _decode_cursor(cursor: str) -> Optional[str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        obj = json.loads(raw)
        return obj.get("sk")
    except Exception:
        return None


class RuntimeEventRepository:
    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def append(self, event: RuntimeEvent) -> RuntimeEvent:
        self.table.put_item(Item=event.to_dynamo_item())
        return event

    def list_for_conversation(
        self,
        agent_id: str,
        conversation_id: str,
        actor_id: str,
        limit: int = 50,
        cursor: Optional[str] = None,
        oldest_first: bool = True,
    ) -> RuntimeEventPage:
        pk = f"Runtime#Agent#{agent_id}#Actor#{actor_id}#Conversation#{conversation_id}"

        exclusive_start_key = None
        if cursor:
            sk = _decode_cursor(cursor)
            if sk:
                exclusive_start_key = {"pk": pk, "sk": sk}

        query_kwargs = {
            "KeyConditionExpression": Key("pk").eq(pk) & Key("sk").begins_with("Event#"),
            "ScanIndexForward": oldest_first,
            "Limit": limit,
        }
        if exclusive_start_key:
            query_kwargs["ExclusiveStartKey"] = exclusive_start_key

        resp = self.table.query(**query_kwargs)

        items = [RuntimeEvent.from_dynamo_item(i) for i in resp.get("Items", [])]

        lek = resp.get("LastEvaluatedKey")
        next_cursor = _encode_cursor(lek["sk"]) if lek else None

        return RuntimeEventPage(items=items, next_cursor=next_cursor, has_more=lek is not None)
