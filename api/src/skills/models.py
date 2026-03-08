"""
Skill package domain models.

These models represent skill packages discovered from the registry
and user-specific configuration stored in DynamoDB.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Registry models (from config.json)
# -----------------------------------------------------------------------------


class SkillPackageConfig(BaseModel):
    """
    Configuration loaded from a skill package's config.json.

    Represents the static metadata of a skill as defined by the skill author.
    """

    skill_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    version: str = Field(..., min_length=1, max_length=50)


class SkillRegistryEntry(BaseModel):
    """
    Entry returned by the skills registry API.

    Contains information needed for the frontend to list available skills
    and determine whether a skill requires user configuration.
    """

    skill_id: str
    name: str
    description: str
    version: str
    has_schema: bool


# -----------------------------------------------------------------------------
# User configuration models (DynamoDB)
# -----------------------------------------------------------------------------


@dataclass
class UserSkillConfig:
    """
    User-specific configuration for an enabled skill.

    Stores the values provided by the user when enabling a skill.
    These values are available at tool execution time.
    """

    user_email: str
    skill_id: str
    config_values: dict[str, Any]
    created_at: str
    updated_at: str

    @property
    def pk(self) -> str:
        return f"User#{self.user_email}"

    @property
    def sk(self) -> str:
        return f"SkillConfig#{self.skill_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "user_email": self.user_email,
            "skill_id": self.skill_id,
            "config_values": self.config_values,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "entity_type": "UserSkillConfig",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "UserSkillConfig":
        return cls(
            user_email=item["user_email"],
            skill_id=item["skill_id"],
            config_values=item.get("config_values", {}),
            created_at=item["created_at"],
            updated_at=item["updated_at"],
        )
