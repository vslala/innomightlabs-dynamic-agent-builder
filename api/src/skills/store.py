"""Skill artifact storage abstraction.

Strategy pattern to allow switching between S3-backed artifacts and local filesystem
artifacts for development/debugging.

A Skill artifact is stored as:
- zip
- manifest.json
- SKILL.md

The DynamoDB SkillDefinition stores keys/paths for these.
"""

from __future__ import annotations

import abc
from src.skills.s3_store import SkillsS3Store


class SkillsStore(abc.ABC):
    @abc.abstractmethod
    def upload_skill_zip(self, owner_email: str, zip_bytes: bytes):
        raise NotImplementedError

    @abc.abstractmethod
    def upload_skill_manifest(self, owner_email: str, manifest, skill_md: str):
        raise NotImplementedError

    @abc.abstractmethod
    def read_text(self, key: str) -> str:
        """Read a UTF-8 text file by key/path."""
        raise NotImplementedError


def get_skills_store() -> SkillsStore:
    """Factory method; selects store strategy based on settings."""
    from src.config import settings
    from src.skills.local_store import LocalSkillsStore

    backend = (settings.skills_store_backend or "s3").lower()
    if backend == "local":
        return LocalSkillsStore(root_dir=settings.skills_local_root)

    # default: s3
    return SkillsS3Store()
