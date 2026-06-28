"""S3 storage helpers for generated conversation media."""

import logging
from datetime import datetime, timezone
from uuid import uuid4

import boto3

from src.config import settings

log = logging.getLogger(__name__)


class ConversationMediaStorage:
    """Store and sign generated media in the private conversation media bucket."""

    def __init__(self):
        self.bucket = settings.conversation_media_bucket
        self.client = boto3.client("s3", region_name=settings.conversation_media_region)

    def build_image_key(
        self,
        *,
        agent_id: str,
        conversation_id: str,
        message_id: str,
        extension: str,
    ) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_extension = extension.lower().lstrip(".") or "png"
        image_suffix = str(uuid4())
        return (
            f"agents/{agent_id}/conversations/{conversation_id}/"
            f"messages/{message_id}/{timestamp}_{image_suffix}.{safe_extension}"
        )

    def put_image(
        self,
        *,
        key: str,
        body: bytes,
        content_type: str,
    ) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )

    def presign_get_url(self, key: str) -> str:
        return str(
            self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=settings.conversation_media_presign_ttl_seconds,
            )
        )

    def get_image(self, key: str) -> tuple[bytes, str]:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        content_type = response.get("ContentType") or "application/octet-stream"
        body = response["Body"].read()
        return body, str(content_type)

    def delete_agent_prefix(self, agent_id: str) -> int:
        return self.delete_prefix(f"agents/{agent_id}/")

    def delete_conversation_prefix(self, agent_id: str, conversation_id: str) -> int:
        return self.delete_prefix(f"agents/{agent_id}/conversations/{conversation_id}/")

    def delete_prefix(self, prefix: str) -> int:
        deleted_count = 0
        paginator = self.client.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if not objects:
                continue

            self.client.delete_objects(
                Bucket=self.bucket,
                Delete={"Objects": objects, "Quiet": True},
            )
            deleted_count += len(objects)

        if deleted_count:
            log.info("Deleted %d conversation media objects under %s", deleted_count, prefix)
        return deleted_count
