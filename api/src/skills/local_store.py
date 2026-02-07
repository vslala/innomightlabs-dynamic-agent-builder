"""Local filesystem skill store.

Used for local development to make artifacts easy to inspect/debug without S3.
Keys stored in DynamoDB are treated as relative paths under root_dir.

Layout matches S3 keys, e.g.:
  innomightlabs/tenants/{owner_email}/skills/{skill_id}/{version}/manifest.json
"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

from src.skills.models import SkillManifest

from .s3_store import UploadedSkillArtifact


class LocalSkillsStore:
    def __init__(self, root_dir: str = "./.skills"):
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _path_for_key(self, key: str) -> Path:
        # Normalize key to a safe relative path
        key = key.lstrip("/")
        return (self.root_dir / key).resolve()

    def read_text(self, key: str) -> str:
        p = self._path_for_key(key)
        return p.read_text(encoding="utf-8")

    def _write_bytes(self, key: str, data: bytes) -> None:
        p = self._path_for_key(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def _write_text(self, key: str, text: str) -> None:
        p = self._path_for_key(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def upload_skill_zip(self, owner_email: str, zip_bytes: bytes) -> UploadedSkillArtifact:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))

        # Validate required files
        names = set(zf.namelist())
        if "manifest.json" not in names:
            raise ValueError("Skill zip missing manifest.json")
        if "SKILL.md" not in names:
            raise ValueError("Skill zip missing SKILL.md")

        manifest_text = zf.read("manifest.json").decode("utf-8")
        skill_md_text = zf.read("SKILL.md").decode("utf-8")
        manifest = SkillManifest.model_validate_json(manifest_text)

        base_prefix = f"innomightlabs/tenants/{owner_email}/skills/{manifest.skill_id}/{manifest.version}"
        zip_key = f"{base_prefix}/skill.zip"
        manifest_key = f"{base_prefix}/manifest.json"
        skill_md_key = f"{base_prefix}/SKILL.md"

        self._write_bytes(zip_key, zip_bytes)
        self._write_text(manifest_key, manifest_text)
        self._write_text(skill_md_key, skill_md_text)

        return UploadedSkillArtifact(
            manifest=manifest,
            skill_md=skill_md_text,
            zip_key=zip_key,
            manifest_key=manifest_key,
            skill_md_key=skill_md_key,
        )

    def upload_skill_manifest(self, owner_email: str, manifest: SkillManifest, skill_md: str) -> UploadedSkillArtifact:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", manifest.model_dump_json())
            z.writestr("SKILL.md", skill_md or "")
        return self.upload_skill_zip(owner_email=owner_email, zip_bytes=buf.getvalue())
