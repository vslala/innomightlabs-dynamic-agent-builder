from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

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
        owner_email: str,
        artifact_id: str,
        filename: str,
    ) -> str:
        scope = hashlib.sha256(owner_email.strip().lower().encode("utf-8")).hexdigest()[:24]
        date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        safe_filename = sanitize_filename(filename)
        return f"users/{scope}/artifacts/{date_prefix}/{artifact_id}/{safe_filename}"

    def put_artifact(self, *, key: str, body: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )

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


def sanitize_filename(filename: str) -> str:
    value = filename.strip().rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    value = SAFE_FILENAME_RE.sub("-", value).strip(".-")
    return value or "artifact"
