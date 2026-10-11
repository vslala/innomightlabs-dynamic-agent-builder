from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, cast

import boto3

from src.config import settings

SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class ArtifactStorage:
    def __init__(self, s3_client: Any | None = None):
        self.bucket = settings.conversation_media_bucket
        self.client = s3_client or boto3.client("s3", region_name=settings.conversation_media_region)

    def build_key(
        self,
        *,
        account_id: str,
        user_id: str,
        artifact_id: str,
        filename: str,
    ) -> str:
        date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        safe_filename = sanitize_filename(filename)
        return f"{member_prefix(account_id, user_id)}/artifacts/{date_prefix}/{artifact_id}/{safe_filename}"

    def put_artifact(self, *, key: str, body: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )

    def delete_artifact(self, key: str) -> None:
        # Exact-key deletion is idempotent for missing objects in the unversioned media bucket.
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def get_object_body(self, key: str) -> bytes:
        return cast(bytes, self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read())

    def presign_get_url(
        self,
        key: str,
        filename: str | None = None,
        *,
        disposition: str = "attachment",
        content_type: str | None = None,
    ) -> str:
        params: dict[str, str] = {
            "Bucket": self.bucket,
            "Key": key,
        }
        if filename:
            params["ResponseContentDisposition"] = f'{disposition}; filename="{sanitize_filename(filename)}"'
        if content_type:
            params["ResponseContentType"] = content_type
        return str(
            self.client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=settings.conversation_media_presign_ttl_seconds,
            )
        )


def member_prefix(account_id: str, user_id: str) -> str:
    """A member's object prefix in an account, as their DynamoDB partition is: ids only, never an email."""
    return f"accounts/{account_id}/members/{user_id}"


def sanitize_filename(filename: str) -> str:
    value = filename.strip().rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    value = SAFE_FILENAME_RE.sub("-", value).strip(".-")
    return value or "artifact"
