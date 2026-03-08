"""
Skills registry: discovers and loads skill packages.

Uses the Strategy pattern to allow different registry backends
(e.g. file system, S3) while keeping a stable interface for the API.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from src.skills.models import SkillPackageConfig, SkillRegistryEntry

log = logging.getLogger(__name__)

CONFIG_FILENAME = "config.json"
SCHEMA_FILENAME = "schema.json"
TOOLS_DIRNAME = "tools"


class SkillsRegistryInterface(ABC):
    """
    Interface for skill package discovery and loading.

    Implementations may scan a file system, remote storage, or other source.
    """

    @abstractmethod
    def list_skills(self) -> list[SkillRegistryEntry]:
        """
        List all available skills in the registry.

        Returns:
            List of registry entries with skill metadata.
        """
        raise NotImplementedError

    @abstractmethod
    def get_schema(self, skill_id: str) -> Optional[dict]:
        """
        Load the form schema for a skill, if it exists.

        Args:
            skill_id: The skill identifier (folder name).

        Returns:
            The schema as a dictionary matching Form format, or None if no schema.
        """
        raise NotImplementedError

    @abstractmethod
    def get_config(self, skill_id: str) -> Optional[SkillPackageConfig]:
        """
        Load the config for a skill.

        Args:
            skill_id: The skill identifier.

        Returns:
            The skill config, or None if not found.
        """
        raise NotImplementedError


class FileSystemSkillsRegistry(SkillsRegistryInterface):
    """
    Registry implementation that scans a directory for skill packages.

    Expects structure:
        skills_root/
            {skill_id}/
                config.json   (required)
                schema.json  (optional)
                tools/       (optional)
    """

    def __init__(self, root_path: Path):
        """
        Initialize the registry with a root path for skill packages.

        Args:
            root_path: Path to the directory containing skill package folders.
        """
        self._root = Path(root_path)
        if not self._root.is_dir():
            log.warning("Skills registry root path does not exist: %s", self._root)

    def list_skills(self) -> list[SkillRegistryEntry]:
        entries: list[SkillRegistryEntry] = []
        if not self._root.exists():
            return entries

        for item in self._root.iterdir():
            if not item.is_dir():
                continue

            skill_id = item.name
            if skill_id.startswith("."):
                continue

            config = self._load_config(item)
            if config is None:
                log.warning("Skipping skill folder without valid config.json: %s", skill_id)
                continue

            schema_path = item / SCHEMA_FILENAME
            has_schema = schema_path.is_file()

            entries.append(
                SkillRegistryEntry(
                    skill_id=config.skill_id,
                    name=config.name,
                    description=config.description,
                    version=config.version,
                    has_schema=has_schema,
                )
            )

        return entries

    def get_schema(self, skill_id: str) -> Optional[dict]:
        skill_dir = self._root / skill_id
        schema_path = skill_dir / SCHEMA_FILENAME

        if not schema_path.is_file():
            return None

        try:
            with open(schema_path, encoding="utf-8") as f:
                data = json.load(f)
            return data
        except (json.JSONDecodeError, OSError) as e:
            log.error("Failed to load schema for skill %s: %s", skill_id, e)
            return None

    def get_config(self, skill_id: str) -> Optional[SkillPackageConfig]:
        skill_dir = self._root / skill_id
        config_path = skill_dir / CONFIG_FILENAME

        if not config_path.is_file():
            return None

        return self._load_config(skill_dir)

    def _load_config(self, skill_dir: Path) -> Optional[SkillPackageConfig]:
        config_path = skill_dir / CONFIG_FILENAME
        if not config_path.is_file():
            return None

        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
            return SkillPackageConfig.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            log.warning("Invalid config.json in %s: %s", skill_dir.name, e)
            return None
