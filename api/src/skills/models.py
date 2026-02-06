"""Skills domain models.

A Skill is a tenant-uploaded package (zip) stored in S3.
We store the canonical artifact in S3 and metadata in DynamoDB.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SkillStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class SkillManifest(BaseModel):
    skill_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    version: str = Field(..., min_length=1, max_length=50)
    description: str = Field(default="", max_length=2000)
    # Tool schemas exposed by this skill (OpenAI tool JSON schema compatible)
    tools: list[dict] = Field(default_factory=list)
    allowed_hosts: list[str] = Field(default_factory=list)


class SkillDefinition(BaseModel):
    owner_email: str
    skill_id: str
    version: str
    name: str
    description: str = ""
    status: SkillStatus = SkillStatus.INACTIVE

    s3_zip_key: str
    s3_manifest_key: str
    s3_skill_md_key: str

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"Tenant#{self.owner_email}"

    @property
    def sk(self) -> str:
        return f"Skill#{self.skill_id}#{self.version}"

    def to_dynamo_item(self) -> dict:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "entity_type": "SkillDefinition",
            "owner_email": self.owner_email,
            "skill_id": self.skill_id,
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "s3_zip_key": self.s3_zip_key,
            "s3_manifest_key": self.s3_manifest_key,
            "s3_skill_md_key": self.s3_skill_md_key,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dynamo_item(cls, item: dict) -> "SkillDefinition":
        return cls(
            owner_email=item["owner_email"],
            skill_id=item["skill_id"],
            version=item["version"],
            name=item.get("name", ""),
            description=item.get("description", ""),
            status=SkillStatus(item.get("status", SkillStatus.INACTIVE.value)),
            s3_zip_key=item["s3_zip_key"],
            s3_manifest_key=item["s3_manifest_key"],
            s3_skill_md_key=item["s3_skill_md_key"],
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )


class SkillDefinitionResponse(BaseModel):
    skill_id: str
    version: str
    name: str
    description: str
    status: SkillStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
