from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

import src.form_models as form_models


class SkillActionManifest(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    handler: str


class SkillManifest(BaseModel):
    id: str
    namespace: str
    name: str
    description: str
    system_prompt: str = ""
    actions: list[SkillActionManifest] = Field(default_factory=list)
    form: list[form_models.FormInput] = Field(default_factory=list)


@dataclass
class LoadedSkill:
    manifest: SkillManifest
    folder_name: str


class SkillCatalogItemResponse(BaseModel):
    skill_id: str
    namespace: str
    name: str
    description: str
    action_names: list[str]
    has_form: bool


class InstalledSkillResponse(BaseModel):
    skill_id: str
    namespace: str
    name: str
    description: str
    enabled: bool
    installed_at: datetime
    updated_at: Optional[datetime] = None
    config: dict[str, Any] = Field(default_factory=dict)
    secret_fields: list[str] = Field(default_factory=list)


class AgentSkill(BaseModel):
    agent_id: str
    skill_id: str
    namespace: str
    skill_name: str
    skill_description: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    encrypted_secrets: str = ""
    secret_fields: list[str] = Field(default_factory=list)
    installed_by: str
    installed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"Agent#{self.agent_id}"

    @property
    def sk(self) -> str:
        return f"Skill#{self.skill_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "entity_type": "AgentSkill",
            "agent_id": self.agent_id,
            "skill_id": self.skill_id,
            "namespace": self.namespace,
            "skill_name": self.skill_name,
            "skill_description": self.skill_description,
            "enabled": self.enabled,
            "config": self.config,
            "encrypted_secrets": self.encrypted_secrets,
            "secret_fields": self.secret_fields,
            "installed_by": self.installed_by,
            "installed_at": self.installed_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "AgentSkill":
        return cls(
            agent_id=item["agent_id"],
            skill_id=item["skill_id"],
            namespace=item.get("namespace", ""),
            skill_name=item.get("skill_name", item["skill_id"]),
            skill_description=item.get("skill_description", ""),
            enabled=bool(item.get("enabled", True)),
            config=item.get("config", {}) or {},
            encrypted_secrets=item.get("encrypted_secrets", ""),
            secret_fields=item.get("secret_fields", []) or [],
            installed_by=item.get("installed_by", ""),
            installed_at=datetime.fromisoformat(item["installed_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )


class InstallSkillRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class UpdateInstalledSkillRequest(BaseModel):
    enabled: Optional[bool] = None
    config: Optional[dict[str, Any]] = None

    @model_validator(mode="after")
    def validate_not_empty(self) -> "UpdateInstalledSkillRequest":
        if self.enabled is None and self.config is None:
            raise ValueError("At least one of 'enabled' or 'config' must be provided")
        return self
