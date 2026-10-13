"""DynamoDB access for the account's vision settings and the uploaded-image ledger."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from src.config import settings
from src.db import get_dynamodb_resource
from src.vision.models import ImageUpload, ImageUploadStatus, VisionSettings


class VisionSettingsRepository:
    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def save(self, vision_settings: VisionSettings) -> VisionSettings:
        existing = self.find_in_account(vision_settings.account_id)
        if existing:
            vision_settings.created_at = existing.created_at
            vision_settings.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=vision_settings.to_dynamo_item())
        return vision_settings

    def find_in_account(self, account_id: str) -> VisionSettings | None:
        item = self.table.get_item(Key={"pk": f"Account#{account_id}", "sk": "VisionSettings"}).get("Item")
        return VisionSettings.from_dynamo_item(item) if item else None


def get_vision_settings_repository() -> VisionSettingsRepository:
    return VisionSettingsRepository()


class ImageUploadRepository:
    """Key: pk `CONVERSATION#{id}`, sk `IMAGE#{image_id}`. Pending rows carry a `ttl`; attaching removes it."""

    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def save(self, upload: ImageUpload) -> ImageUpload:
        self.table.put_item(Item=upload.to_dynamo_item())
        return upload

    def find(self, conversation_id: str, image_id: str) -> ImageUpload | None:
        item = self.table.get_item(Key={"pk": f"CONVERSATION#{conversation_id}", "sk": f"IMAGE#{image_id}"}).get("Item")
        return ImageUpload.from_dynamo_item(item) if item else None

    def claim(self, conversation_id: str, image_id: str, *, uploaded_by: str) -> ImageUpload | None:
        """Mark a pending upload as sent with a message. Only its uploader may, once, and before it expires.

        The conditions run in DynamoDB, so two sends racing for one image cannot both win. DynamoDB's own TTL
        deletion can lag, which is why expiry is part of the condition as well.
        """
        try:
            response = self.table.update_item(
                Key={"pk": f"CONVERSATION#{conversation_id}", "sk": f"IMAGE#{image_id}"},
                UpdateExpression="SET #status = :attached REMOVE #ttl",
                ConditionExpression="#status = :pending AND uploaded_by = :actor AND #ttl > :now",
                ExpressionAttributeNames={"#status": "status", "#ttl": "ttl"},
                ExpressionAttributeValues={
                    ":attached": ImageUploadStatus.ATTACHED,
                    ":pending": ImageUploadStatus.PENDING,
                    ":actor": uploaded_by,
                    ":now": int(time.time()),
                },
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise
        return ImageUpload.from_dynamo_item(response["Attributes"])
