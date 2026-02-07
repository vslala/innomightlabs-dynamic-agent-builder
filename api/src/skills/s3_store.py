"""S3 storage helpers for skills."""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from typing import Optional

import boto3

from src.config import settings
from .models import SkillManifest


@dataclass
class UploadedSkillArtifact:
    manifest: SkillManifest
    skill_md: str
    zip_key: str
    manifest_key: str
    skill_md_key: str


class SkillsS3Store:
    def __init__(self):
        if not settings.skills_bucket_name:
            raise ValueError("SKILLS_BUCKET_NAME is not configured")
        self.bucket = settings.skills_bucket_name
        self.s3 = boto3.client("s3", region_name=settings.aws_region)

    def read_text(self, key: str) -> str:
        obj = self.s3.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read().decode("utf-8")

    def upload_skill_manifest(self, owner_email: str, manifest: SkillManifest, skill_md: str) -> UploadedSkillArtifact:
        """Create a zip from manifest + SKILL.md and upload using the same layout as zip upload."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", manifest.model_dump_json())
            z.writestr("SKILL.md", skill_md or "")
        return self.upload_skill_zip(owner_email=owner_email, zip_bytes=buf.getvalue())

    def _tenant_prefix(self, owner_email: str, skill_id: str, version: str) -> str:
        return f"innomightlabs/tenants/{owner_email}/skills/{skill_id}/{version}".rstrip("/")

    def upload_skill_zip(self, owner_email: str, zip_bytes: bytes) -> UploadedSkillArtifact:
        # Read zip
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))

        if "manifest.json" not in zf.namelist():
            raise ValueError("Skill zip missing manifest.json")
        if "SKILL.md" not in zf.namelist():
            raise ValueError("Skill zip missing SKILL.md")

        manifest_raw = zf.read("manifest.json").decode("utf-8")
        skill_md = zf.read("SKILL.md").decode("utf-8")

        manifest = SkillManifest.model_validate_json(manifest_raw)

        prefix = self._tenant_prefix(owner_email, manifest.skill_id, manifest.version)
        zip_key = f"{prefix}/skill.zip"
        manifest_key = f"{prefix}/manifest.json"
        skill_md_key = f"{prefix}/SKILL.md"

        # Upload zip + extracted files (fast reads)
        self.s3.put_object(Bucket=self.bucket, Key=zip_key, Body=zip_bytes, ContentType="application/zip")
        self.s3.put_object(Bucket=self.bucket, Key=manifest_key, Body=manifest_raw.encode("utf-8"), ContentType="application/json")
        self.s3.put_object(Bucket=self.bucket, Key=skill_md_key, Body=skill_md.encode("utf-8"), ContentType="text/markdown")

        return UploadedSkillArtifact(
            manifest=manifest,
            skill_md=skill_md,
            zip_key=zip_key,
            manifest_key=manifest_key,
            skill_md_key=skill_md_key,
        )

    def get_skill_md(self, key: str) -> str:
        obj = self.s3.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read().decode("utf-8")

    def get_manifest(self, key: str) -> SkillManifest:
        obj = self.s3.get_object(Bucket=self.bucket, Key=key)
        raw = obj["Body"].read().decode("utf-8")
        return SkillManifest.model_validate_json(raw)
