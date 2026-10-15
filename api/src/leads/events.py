"""Lead events: the durable "this lead was captured" note that starts the automations listening for it.

A capture saves its event in the same transaction, so a lead and the note about it exist together or not at all. The
scheduler's lead-event dispatcher (`automations/triggers/lead_captured.py`) then works through the events, so starting
the automations never slows a capture and survives a restart.

An event is pending while it has `gsi2_pk`/`gsi2_sk`. `gsi2_sk` is when it is next due, which is also its lease: a
worker takes an event by moving that time forward, with a condition on the value it read, so of several workers
(replicas, a retried pass) only one gets it. One that dies leaves the event to come due again.

Key: `Account#{account_id}` / `LeadEvent#{capture_id}`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field

from src.config import settings
from src.db import get_dynamodb_resource

#: The index partition every event waiting for a worker is in
PENDING_PARTITION = "LeadEventPending"
#: How long a worker has to start the runs before another may take the event
LEASE = timedelta(minutes=2)
#: The first retry waits this long; each next one twice as long
FIRST_RETRY_DELAY = timedelta(seconds=30)
MAX_ATTEMPTS = 5
#: Finished events stay a while for debugging, then DynamoDB's TTL removes them
DONE_KEPT = timedelta(days=1)
FAILED_KEPT = timedelta(days=14)


def _at(moment: datetime) -> str:
    """Times as the index sorts them: ISO 8601 in UTC, so text order is time order."""
    return moment.astimezone(timezone.utc).isoformat()


class LeadEvent(BaseModel):
    account_id: str
    capture_id: str
    attempts: int = 0
    #: Automation triggers whose run is already started, so a retry doesn't start them twice
    started: set[str] = Field(default_factory=set)
    status: Literal["pending", "done", "failed"] = "pending"
    due_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def key(self) -> dict[str, str]:
        return {"pk": f"Account#{self.account_id}", "sk": f"LeadEvent#{self.capture_id}"}

    def to_dynamo_item(self) -> dict[str, Any]:
        """A new event: pending, due now."""
        return {
            **self.key,
            "entity_type": "LeadEvent",
            "account_id": self.account_id,
            "capture_id": self.capture_id,
            "attempts": self.attempts,
            "status": self.status,
            "gsi2_pk": PENDING_PARTITION,
            "gsi2_sk": _at(self.due_at),
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> LeadEvent:
        return cls(
            account_id=item["account_id"],
            capture_id=item["capture_id"],
            attempts=int(item.get("attempts", 0)),
            started=set(item.get("started", set())),
            status=item.get("status", "pending"),
            due_at=datetime.fromisoformat(item["gsi2_sk"]) if "gsi2_sk" in item else datetime.now(timezone.utc),
        )


class LeadEventRepository:
    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def due(self, now: datetime, limit: int) -> list[LeadEvent]:
        response = self.table.query(
            IndexName="gsi2",
            KeyConditionExpression=Key("gsi2_pk").eq(PENDING_PARTITION) & Key("gsi2_sk").lte(_at(now)),
            Limit=limit,
        )
        return [LeadEvent.from_dynamo_item(item) for item in response.get("Items", [])]

    def claim(self, event: LeadEvent, now: datetime) -> LeadEvent | None:
        """Take the event for one attempt, or None when another worker got there first."""
        try:
            response = self.table.update_item(
                Key=event.key,
                UpdateExpression="SET gsi2_sk = :lease, attempts = attempts + :one",
                ConditionExpression="gsi2_sk = :seen",
                ExpressionAttributeValues={":seen": _at(event.due_at), ":lease": _at(now + LEASE), ":one": 1},
                ReturnValues="ALL_NEW",
            )
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise
        return LeadEvent.from_dynamo_item(response["Attributes"])

    def record_started(self, event: LeadEvent, trigger_id: str) -> None:
        self.table.update_item(
            Key=event.key, UpdateExpression="ADD started :trigger", ExpressionAttributeValues={":trigger": {trigger_id}}
        )

    def complete(self, event: LeadEvent, now: datetime) -> None:
        self._finish(event, "done", now + DONE_KEPT)

    def retry_later(self, event: LeadEvent, now: datetime) -> LeadEvent:
        """Due again after a wait that doubles each attempt, or given up on after the last. `event` is as claimed,
        so its `attempts` includes this one."""
        if event.attempts >= MAX_ATTEMPTS:
            self._finish(event, "failed", now + FAILED_KEPT)
            return event.model_copy(update={"status": "failed"})
        due_at = now + FIRST_RETRY_DELAY * 2 ** (event.attempts - 1)
        self.table.update_item(
            Key=event.key,
            UpdateExpression="SET gsi2_sk = :due",
            ExpressionAttributeValues={":due": _at(due_at)},
        )
        return event.model_copy(update={"due_at": due_at})

    def _finish(self, event: LeadEvent, status: str, keep_until: datetime) -> None:
        self.table.update_item(
            Key=event.key,
            UpdateExpression="SET #status = :status, #ttl = :ttl REMOVE gsi2_pk, gsi2_sk",
            ExpressionAttributeNames={"#status": "status", "#ttl": "ttl"},
            ExpressionAttributeValues={":status": status, ":ttl": int(keep_until.timestamp())},
        )
