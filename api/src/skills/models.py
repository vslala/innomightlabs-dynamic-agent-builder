"""Skills domain models.

A Skill is a tenant-uploaded package (zip) stored in S3.
We store the canonical artifact in S3 and metadata in DynamoDB.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SkillStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class SkillToolExecutor(str, Enum):
    HTTP = "http"


class HttpToolSpec(BaseModel):
    method: str = Field(..., description="HTTP method: GET/POST/PUT/PATCH/DELETE")
    url: str = Field(..., min_length=1, description="Full http(s) URL")
    headers: dict[str, Any] | None = None
    query: dict[str, Any] | None = None
    json_body: Any | None = None
    text_body: str | None = None


class SkillToolDefinition(BaseModel):
    """Strict tool definition stored in a skill manifest."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    # OpenAI/Anthropic style tool schema
    parameters: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})

    executor: SkillToolExecutor = Field(...)

    # Executor-specific config
    http: HttpToolSpec | None = None

    def validate_executor_config(self) -> "SkillToolDefinition":
        if self.executor == SkillToolExecutor.HTTP:
            if self.http is None:
                raise ValueError("executor=http requires http spec")
            m = self.http.method.upper().strip()
            if m not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                raise ValueError("http.method must be one of GET/POST/PUT/PATCH/DELETE")
            self.http.method = m
        return self


class SkillManifest(BaseModel):
    skill_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    version: str = Field(..., min_length=1, max_length=50)
    description: str = Field(default="", max_length=2000)
    allowed_hosts: list[str] = Field(default_factory=list)

    tools: list[SkillToolDefinition] = Field(default_factory=list, description="Strict tool definitions")

    def model_post_init(self, __context: Any) -> None:
        # Ensure each tool has valid executor config
        for t in self.tools:
            t.validate_executor_config()


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
