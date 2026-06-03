from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

import src.form_models as form_models


class SkillConnectorDependency(BaseModel):
    connector_id: str
    required: bool = True


class SkillConnectorStatus(BaseModel):
    connector_id: str
    provider_name: str
    required: bool = True
    connected: bool = False
    connect_path: Optional[str] = None


class SkillAutomationConfig(BaseModel):
    enabled: bool = True


class SkillLifecycleHook(BaseModel):
    handler: str


class SkillLifecycleManifest(BaseModel):
    delete: Optional[SkillLifecycleHook] = None
    create: Optional[SkillLifecycleHook] = None
    update: Optional[SkillLifecycleHook] = None
    enable: Optional[SkillLifecycleHook] = None
    disable: Optional[SkillLifecycleHook] = None


class SkillActionAutomationConfig(BaseModel):
    enabled: bool = True


class SkillActionManifest(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    action_form: Optional[form_models.Form] = None
    automation: SkillActionAutomationConfig = Field(default_factory=SkillActionAutomationConfig)
    lifecycle: SkillLifecycleManifest = Field(default_factory=SkillLifecycleManifest)
    handler: str


class SkillManifest(BaseModel):
    id: str
    namespace: str
    name: str
    description: str
    system_prompt: str = ""
    repeatable: bool = False
    repeatable_identity_fields: list[str] = Field(default_factory=list)

    # Optional skill-owned API router (mounted under /skills/{skill_id}/...)
    # Format: "module_path:attribute" or "module_path.attribute".
    # Example: "router:router" (resolves to src.skills.<skill_folder>.router.router)
    api_router: Optional[str] = None

    requires_oauth: bool = False
    oauth_provider_name: Optional[str] = None
    connectors: list[SkillConnectorDependency] = Field(default_factory=list)
    automation: SkillAutomationConfig = Field(default_factory=SkillAutomationConfig)
    lifecycle: SkillLifecycleManifest = Field(default_factory=SkillLifecycleManifest)
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
    requires_oauth: bool = False
    oauth_provider_name: Optional[str] = None
    oauth_connected: Optional[bool] = None
    oauth_start_path: Optional[str] = None
    connectors: list[SkillConnectorStatus] = Field(default_factory=list)
    available: bool = True
    repeatable: bool = False


class InstalledSkillResponse(BaseModel):
    installed_skill_id: str
    skill_id: str
    namespace: str
    name: str
    description: str
    enabled: bool
    installed_at: datetime
    updated_at: Optional[datetime] = None
    config: dict[str, Any] = Field(default_factory=dict)
    secret_fields: list[str] = Field(default_factory=list)
    requires_oauth: bool = False
    oauth_provider_name: Optional[str] = None


class AgentSkill(BaseModel):
    agent_id: str
    installed_skill_id: str = ""
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
        return f"Skill#{self.installed_skill_id or self.skill_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "entity_type": "AgentSkill",
            "agent_id": self.agent_id,
            "installed_skill_id": self.installed_skill_id or self.skill_id,
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
        skill_id = item["skill_id"]
        return cls(
            agent_id=item["agent_id"],
            installed_skill_id=item.get("installed_skill_id", skill_id),
            skill_id=skill_id,
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
