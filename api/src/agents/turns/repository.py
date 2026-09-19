"""DynamoDB persistence for ConversationTurn.

See api/docs/LLD-async-chat-turns.md ("Data Model") for why these three access
patterns need no new GSI: `gsi2` already exists for id lookups, and turn rows
live in the same `CONVERSATION#` partition as messages without colliding with
any message query (all of which filter on the `MESSAGE#` sort-key prefix).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from src.agents.turns.models import ConversationTurn, ConversationTurnStatus
from src.config import settings
from src.db import get_dynamodb_resource

log = logging.getLogger(__name__)

_STALE_TURN_ERROR = (
    "This response stopped before it finished because the server restarted. "
    "Please send the message again."
)


class ConversationTurnRepository:
    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def create(self, turn: ConversationTurn) -> ConversationTurn:
        self.table.put_item(
            Item=turn.to_dynamo_item(),
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        return turn

    def find_by_id(self, turn_id: str) -> ConversationTurn | None:
        response = self.table.query(
            IndexName="gsi2",
            KeyConditionExpression=Key("gsi2_pk").eq(f"ConversationTurn#{turn_id}")
            & Key("gsi2_sk").eq(f"ConversationTurn#{turn_id}"),
            Limit=1,
        )
        items = response.get("Items", [])
        if not items:
            return None
        return ConversationTurn.from_dynamo_item(items[0])

    def find_active(self, conversation_id: str) -> ConversationTurn | None:
        """The newest turn for a conversation, if it is still running."""
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"CONVERSATION#{conversation_id}")
            & Key("sk").begins_with("TURN#"),
            ScanIndexForward=False,
            Limit=1,
        )
        items = response.get("Items", [])
        if not items:
            return None
        turn = ConversationTurn.from_dynamo_item(items[0])
        if turn.status != ConversationTurnStatus.RUNNING:
            return None
        return turn

    def heartbeat(self, turn: ConversationTurn) -> None:
        heartbeat_at = datetime.now(timezone.utc)
        self.table.update_item(
            Key={"pk": turn.pk, "sk": turn.sk},
            UpdateExpression="SET last_heartbeat_at = :heartbeat",
            ExpressionAttributeValues={":heartbeat": _iso(heartbeat_at)},
        )
        turn.last_heartbeat_at = heartbeat_at

    def finish(
        self,
        turn: ConversationTurn,
        status: ConversationTurnStatus,
        *,
        error: str | None = None,
        assistant_message_id: str | None = None,
    ) -> ConversationTurn:
        turn.status = status
        turn.error = error
        turn.completed_at = datetime.now(timezone.utc)
        if assistant_message_id:
            turn.assistant_message_id = assistant_message_id
        self.table.put_item(Item=turn.to_dynamo_item())
        return turn

    def fail_stale_turns(self, *, now: datetime | None = None) -> int:
        """Fail every `running` turn whose heartbeat is older than the stale timeout.

        Called from the reaper, never salvages partial text: by the time a turn
        is stale, the process that held its response is gone.
        """
        checked_at = now or datetime.now(timezone.utc)
        failed_count = 0

        for turn in self._find_running():
            if not turn.is_stale(
                stale_after_seconds=settings.chat_turn_stale_timeout_seconds, now=checked_at
            ):
                continue
            if self._mark_failed_if_heartbeat_unchanged(turn, failed_at=checked_at):
                failed_count += 1

        return failed_count

    def _find_running(self) -> list[ConversationTurn]:
        scan_args: dict[str, Any] = {
            "FilterExpression": (
                Attr("entity_type").eq("ConversationTurn")
                & Attr("status").eq(ConversationTurnStatus.RUNNING.value)
            )
        }
        items: list[dict] = []

        while True:
            response = self.table.scan(**scan_args)
            items.extend(response.get("Items", []))
            last_evaluated_key = response.get("LastEvaluatedKey")
            if not last_evaluated_key:
                break
            scan_args["ExclusiveStartKey"] = last_evaluated_key

        return [ConversationTurn.from_dynamo_item(item) for item in items]

    def _mark_failed_if_heartbeat_unchanged(
        self, turn: ConversationTurn, *, failed_at: datetime
    ) -> bool:
        """Fail a stale turn only if no newer heartbeat won the scan/write race."""
        expression_values: dict[str, Any] = {
            ":running": ConversationTurnStatus.RUNNING.value,
            ":failed": ConversationTurnStatus.FAILED.value,
            ":failed_at": _iso(failed_at),
            ":error": _STALE_TURN_ERROR,
        }
        if turn.last_heartbeat_at is not None:
            condition = "#status = :running AND last_heartbeat_at = :observed_heartbeat"
            expression_values[":observed_heartbeat"] = _iso(turn.last_heartbeat_at)
        else:
            condition = (
                "#status = :running AND "
                "(attribute_not_exists(last_heartbeat_at) OR last_heartbeat_at = :empty_heartbeat)"
            )
            expression_values[":empty_heartbeat"] = None

        try:
            self.table.update_item(
                Key={"pk": turn.pk, "sk": turn.sk},
                UpdateExpression="SET #status = :failed, #error = :error, completed_at = :failed_at",
                ConditionExpression=condition,
                ExpressionAttributeNames={"#status": "status", "#error": "error"},
                ExpressionAttributeValues=expression_values,
            )
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise


def _iso(value: datetime) -> str:
    """Match pydantic's JSON datetime encoding (`Z` for UTC), since `to_dynamo_item()`
    writes timestamps that way — a raw `.isoformat()` (`+00:00`) would never equal a
    value already stored via `to_dynamo_item()`, silently breaking every conditional
    write here.
    """
    return value.isoformat().replace("+00:00", "Z")
