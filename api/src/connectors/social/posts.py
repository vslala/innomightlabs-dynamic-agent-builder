"""One record per (post, account): what happened when we asked a network to publish. It is also the lock that keeps a
retried automation step or a repeated agent call from posting the same thing twice."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field

from src.config import settings
from src.db import get_dynamodb_resource
from src.utils.dynamodb import convert_decimals

RETENTION = timedelta(days=180)


class TargetStatus(str, Enum):
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    #: The create call may or may not have gone through. Never retried automatically.
    UNCERTAIN = "uncertain"
    SKIPPED = "skipped"


class PostTarget(BaseModel):
    account_id: str
    post_id: str
    social_account_id: str
    network: str
    handle: str
    status: TargetStatus
    reason: str = ""
    detail: str = ""
    url: Optional[str] = None
    external_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": f"Account#{self.account_id}",
            "sk": f"SocialPost#{self.post_id}#{self.social_account_id}",
            "entity_type": "SocialPostTarget",
            **{key: value for key, value in self.model_dump(mode="json").items() if value is not None},
            "ttl": int((self.created_at + RETENTION).timestamp()),
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "PostTarget":
        item = convert_decimals(item)
        return cls(**{key: item[key] for key in cls.model_fields if key in item})

    def to_result(self) -> dict[str, Any]:
        """What the agent and the automation see. The record holds no text and no credentials."""
        result: dict[str, Any] = {"network": self.network, "handle": self.handle, "status": self.status.value}
        for key in ("url", "reason", "detail"):
            if getattr(self, key):
                result[key] = getattr(self, key)
        return result


class SocialPostRepository:
    """
    Key structure (single table):
        pk: Account#{account_id}   sk: SocialPost#{post_id}#{social_account_id}
    """

    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def claim(self, target: PostTarget) -> Optional[PostTarget]:
        """Take the right to publish this target. None when it was already published, is in flight, or may exist."""
        try:
            self.table.put_item(Item=target.to_dynamo_item(), ConditionExpression="attribute_not_exists(pk)")
            return target
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
        # A failed target (nothing was created) may be tried again, once, by whoever wins this update
        try:
            self.table.update_item(
                Key=self._key(target),
                UpdateExpression="SET #status = :publishing REMOVE reason, detail",
                ConditionExpression="#status = :failed",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":publishing": TargetStatus.PUBLISHING.value, ":failed": TargetStatus.FAILED.value},
            )
            return target
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            return None

    def get(self, target: PostTarget) -> PostTarget:
        item = self.table.get_item(Key=self._key(target)).get("Item")
        return PostTarget.from_dynamo_item(item) if item else target

    def finish(self, target: PostTarget, status: TargetStatus, *, reason: str = "", detail: str = "",
               url: str | None = None, external_id: str | None = None) -> PostTarget:
        done = target.model_copy(update={"status": status, "reason": reason, "detail": detail,
                                         "url": url, "external_id": external_id})
        self.table.put_item(Item=done.to_dynamo_item())
        return done

    def list(self, account_id: str, post_id: str) -> list[PostTarget]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"Account#{account_id}") & Key("sk").begins_with(f"SocialPost#{post_id}#")
        )
        return [PostTarget.from_dynamo_item(item) for item in response.get("Items", [])]

    @staticmethod
    def _key(target: PostTarget) -> dict[str, str]:
        return {"pk": f"Account#{target.account_id}", "sk": f"SocialPost#{target.post_id}#{target.social_account_id}"}
