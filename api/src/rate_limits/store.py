"""Atomic storage operations the rate limit strategies are built from."""

from __future__ import annotations

from typing import Any, Protocol

from botocore.exceptions import ClientError

from src.config import settings
from src.db import get_dynamodb_resource


class RateLimitStore(Protocol):
    def add(self, pk: str, sk: str, delta: int, ttl: int) -> int:
        """Atomically add `delta` to a counter and return its new value."""
        ...

    def count(self, pk: str, sk: str) -> int:
        """A counter's current value; 0 when it doesn't exist."""
        ...

    def claim(self, pk: str, sk: str, now: int, expires_at: int) -> bool:
        """Take a lock unless someone holds one that hasn't expired by `now`."""
        ...

    def claim_expiry(self, pk: str, sk: str) -> int | None:
        """When the current lock expires; None when there is none."""
        ...

    def release_claim(self, pk: str, sk: str, expires_at: int) -> None:
        """Remove a lock, but only the one that expires at `expires_at`."""
        ...


class DynamoRateLimitStore:
    """Rate limit items live in the main table under `RATE_LIMIT#{scope}#{subject hash}`."""

    def __init__(self, table: Any = None):
        self.table = table or get_dynamodb_resource().Table(settings.dynamodb_table)

    def add(self, pk: str, sk: str, delta: int, ttl: int) -> int:
        response = self.table.update_item(
            Key={"pk": pk, "sk": sk},
            UpdateExpression="ADD #count :delta SET #ttl = if_not_exists(#ttl, :ttl)",
            ExpressionAttributeNames={"#count": "count", "#ttl": "ttl"},
            ExpressionAttributeValues={":delta": delta, ":ttl": ttl},
            ReturnValues="UPDATED_NEW",
        )
        return int(response["Attributes"]["count"])

    def count(self, pk: str, sk: str) -> int:
        item = self.table.get_item(Key={"pk": pk, "sk": sk}, ConsistentRead=True).get("Item")
        return int(item["count"]) if item else 0

    def claim(self, pk: str, sk: str, now: int, expires_at: int) -> bool:
        try:
            self.table.put_item(
                Item={"pk": pk, "sk": sk, "expires_at": expires_at, "ttl": expires_at},
                # An expired lock is free even if TTL hasn't deleted it yet.
                ConditionExpression="attribute_not_exists(pk) OR expires_at <= :now",
                ExpressionAttributeValues={":now": now},
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def claim_expiry(self, pk: str, sk: str) -> int | None:
        item = self.table.get_item(Key={"pk": pk, "sk": sk}, ConsistentRead=True).get("Item")
        return int(item["expires_at"]) if item else None

    def release_claim(self, pk: str, sk: str, expires_at: int) -> None:
        try:
            self.table.delete_item(
                Key={"pk": pk, "sk": sk},
                ConditionExpression="expires_at = :expires_at",
                ExpressionAttributeValues={":expires_at": expires_at},
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
