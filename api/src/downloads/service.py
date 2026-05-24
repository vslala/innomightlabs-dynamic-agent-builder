"""S3-backed plugin downloads service."""

from __future__ import annotations

import json
import logging
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from src.config import settings
from src.downloads.models import PluginDownloadDetail, PluginDownloadSummary

log = logging.getLogger(__name__)


class DownloadsConfigurationError(Exception):
    """Raised when downloads are not configured."""


class PluginDownloadNotFoundError(Exception):
    """Raised when a requested plugin is not present in the manifest."""


class DownloadsService:
    """Load plugin manifests from S3 and generate short-lived download URLs."""

    def __init__(self, s3_client: Any | None = None):
        self._s3 = s3_client or boto3.client("s3", region_name=settings.downloads_artifacts_region)

    def list_plugins(self) -> list[PluginDownloadSummary]:
        manifest = self._load_manifest()
        return [
            self._build_summary(plugin)
            for plugin in manifest.get("plugins", [])
            if isinstance(plugin, dict)
        ]

    def get_plugin_detail(self, plugin_id: str) -> PluginDownloadDetail:
        plugin = self._find_plugin(plugin_id)
        summary = self._build_summary(plugin)
        readme_markdown = self._read_text_object(str(plugin.get("readme_key", "")))

        return PluginDownloadDetail(
            **summary.model_dump(),
            readme_markdown=readme_markdown,
        )

    def _find_plugin(self, plugin_id: str) -> dict[str, Any]:
        manifest = self._load_manifest()
        for plugin in manifest.get("plugins", []):
            if isinstance(plugin, dict) and plugin.get("id") == plugin_id:
                return plugin
        raise PluginDownloadNotFoundError(plugin_id)

    def _load_manifest(self) -> dict[str, Any]:
        key = settings.downloads_manifest_key
        if not settings.downloads_artifacts_bucket or not key:
            raise DownloadsConfigurationError("Downloads artifacts bucket is not configured")

        try:
            return json.loads(self._read_text_object(key))
        except json.JSONDecodeError as exc:
            log.exception("Downloads manifest is not valid JSON")
            raise DownloadsConfigurationError("Downloads manifest is invalid") from exc

    def _read_text_object(self, key: str) -> str:
        if not key:
            return ""

        try:
            response = self._s3.get_object(
                Bucket=settings.downloads_artifacts_bucket,
                Key=key,
            )
            return response["Body"].read().decode("utf-8")
        except (ClientError, BotoCoreError) as exc:
            log.exception("Failed to read downloads artifact from S3: %s", key)
            raise DownloadsConfigurationError("Downloads artifacts are unavailable") from exc

    def _build_summary(self, plugin: dict[str, Any]) -> PluginDownloadSummary:
        artifact = plugin.get("artifact")
        if not isinstance(artifact, dict):
            raise DownloadsConfigurationError("Downloads manifest plugin is missing artifact metadata")

        artifact_key = str(artifact.get("key", ""))
        icon_key = str(plugin.get("icon_key", ""))
        filename = str(artifact.get("filename") or artifact_key.rsplit("/", 1)[-1])

        return PluginDownloadSummary(
            id=str(plugin.get("id", "")),
            name=str(plugin.get("name", "")),
            kind=str(plugin.get("kind", "")),
            tagline=str(plugin.get("tagline", "")),
            description=str(plugin.get("description", "")),
            version=str(plugin.get("version", "")),
            platform=str(plugin.get("platform", "")),
            filename=filename,
            download_url=self._presign_object(artifact_key, filename=filename),
            icon_url=self._presign_object(icon_key) if icon_key else None,
            size_bytes=artifact.get("size_bytes") if isinstance(artifact.get("size_bytes"), int) else None,
            sha256=artifact.get("sha256") if isinstance(artifact.get("sha256"), str) else None,
        )

    def _presign_object(self, key: str, filename: str | None = None) -> str:
        if not key:
            return ""

        params: dict[str, str] = {
            "Bucket": settings.downloads_artifacts_bucket,
            "Key": key,
        }
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'

        return self._s3.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=settings.downloads_presign_ttl_seconds,
        )
