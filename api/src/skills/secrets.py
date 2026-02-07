"""Skill secrets (tenant-provided secret variables).

Secrets are linked to (tenant, skill_id, secret_name).
They are version-agnostic by design.

Values are encrypted at rest using the same encrypt/decrypt helpers used elsewhere.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class SkillSecret(BaseModel):
    owner_email: str
    skill_id: str
    name: str = Field(..., min_length=1, max_length=100)

    encrypted_value: str

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"Tenant#{self.owner_email}"

    @property
    def sk(self) -> str:
        return f"SkillSecret#{self.skill_id}#{self.name}"

    def to_dynamo_item(self) -> dict:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "entity_type": "SkillSecret",
            "owner_email": self.owner_email,
            "skill_id": self.skill_id,
            "name": self.name,
            "encrypted_value": self.encrypted_value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dynamo_item(cls, item: dict) -> "SkillSecret":
        return cls(
            owner_email=item["owner_email"],
            skill_id=item["skill_id"],
            name=item["name"],
            encrypted_value=item["encrypted_value"],
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )
