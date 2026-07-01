from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from src.agents.models import AgentResponse
from src.form_models import Form
from src.utils.dynamodb import convert_decimals


class MarketplaceAgentStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class MarketplaceAgentSkillTemplate(BaseModel):
    template_skill_key: str
    skill_id: str
    display_name: str | None = None
    description: str | None = None
    required: bool = True
    enabled_on_import: bool = True
    default_config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize(self) -> "MarketplaceAgentSkillTemplate":
        self.template_skill_key = self.template_skill_key.strip()
        self.skill_id = self.skill_id.strip()
        if not self.template_skill_key:
            raise ValueError("template_skill_key is required")
        if not self.skill_id:
            raise ValueError("skill_id is required")
        return self


class MarketplaceAgentTemplate(BaseModel):
    template_id: str = Field(default_factory=lambda: f"template_{uuid4()}")
    title: str
    slug: str = ""
    template_version: int = 1
    parent_template_id: str | None = None
    latest_template_id: str | None = None
    changelog: str | None = None
    short_description: str
    full_description: str
    agent_name: str
    agent_architecture: str
    agent_provider: str
    agent_model: str | None = None
    allow_model_override: bool = True
    agent_persona: str
    agent_description: str | None = None
    skills: list[MarketplaceAgentSkillTemplate] = Field(default_factory=list)
    source_agent_id: str | None = None
    publisher_user_email: str | None = None
    publisher_display_name: str = "InnomightLabs"
    tags: list[str] = Field(default_factory=list)
    status: MarketplaceAgentStatus = MarketplaceAgentStatus.DRAFT
    import_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def normalize(self) -> "MarketplaceAgentTemplate":
        self.title = self.title.strip()
        self.slug = self.slug.strip() or slugify(self.title)
        self.short_description = self.short_description.strip()
        self.full_description = self.full_description.strip()
        self.agent_name = self.agent_name.strip()
        self.agent_architecture = self.agent_architecture.strip()
        self.agent_provider = self.agent_provider.strip()
        self.agent_model = self.agent_model.strip() if self.agent_model else None
        self.agent_persona = self.agent_persona.strip()
        self.agent_description = self.agent_description.strip() if self.agent_description else None
        self.tags = [tag.strip().lower() for tag in self.tags if tag.strip()]
        self.parent_template_id = self.parent_template_id or self.template_id
        self.latest_template_id = self.latest_template_id or self.template_id
        if not self.title:
            raise ValueError("title is required")
        if not self.short_description:
            raise ValueError("short_description is required")
        if not self.full_description:
            raise ValueError("full_description is required")
        if not self.agent_name:
            raise ValueError("agent_name is required")
        if not self.agent_persona:
            raise ValueError("agent_persona is required")
        return self

    @property
    def pk(self) -> str:
        return "MarketplaceAgent"

    @property
    def sk(self) -> str:
        return f"Template#{self.template_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "entity_type": "MarketplaceAgentTemplate",
            "template_id": self.template_id,
            "title": self.title,
            "slug": self.slug,
            "template_version": self.template_version,
            "parent_template_id": self.parent_template_id,
            "latest_template_id": self.latest_template_id,
            "changelog": self.changelog,
            "short_description": self.short_description,
            "full_description": self.full_description,
            "agent_name": self.agent_name,
            "agent_architecture": self.agent_architecture,
            "agent_provider": self.agent_provider,
            "agent_model": self.agent_model,
            "allow_model_override": self.allow_model_override,
            "agent_persona": self.agent_persona,
            "agent_description": self.agent_description,
            "skills": [skill.model_dump(mode="json") for skill in self.skills],
            "source_agent_id": self.source_agent_id,
            "publisher_user_email": self.publisher_user_email,
            "publisher_display_name": self.publisher_display_name,
            "tags": self.tags,
            "status": self.status.value,
            "import_count": self.import_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "MarketplaceAgentTemplate":
        data = convert_decimals(item)
        return cls(
            template_id=data["template_id"],
            title=data["title"],
            slug=data.get("slug", ""),
            template_version=data.get("template_version", 1),
            parent_template_id=data.get("parent_template_id"),
            latest_template_id=data.get("latest_template_id"),
            changelog=data.get("changelog"),
            short_description=data["short_description"],
            full_description=data["full_description"],
            agent_name=data["agent_name"],
            agent_architecture=data["agent_architecture"],
            agent_provider=data["agent_provider"],
            agent_model=data.get("agent_model"),
            allow_model_override=bool(data.get("allow_model_override", True)),
            agent_persona=data["agent_persona"],
            agent_description=data.get("agent_description"),
            skills=[MarketplaceAgentSkillTemplate(**skill) for skill in data.get("skills", [])],
            source_agent_id=data.get("source_agent_id"),
            publisher_user_email=data.get("publisher_user_email"),
            publisher_display_name=data.get("publisher_display_name", "InnomightLabs"),
            tags=data.get("tags", []) or [],
            status=MarketplaceAgentStatus(data.get("status", MarketplaceAgentStatus.DRAFT.value)),
            import_count=data.get("import_count", 0),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
        )

    def to_summary_response(self) -> "MarketplaceAgentSummaryResponse":
        return MarketplaceAgentSummaryResponse(
            template_id=self.template_id,
            title=self.title,
            slug=self.slug,
            short_description=self.short_description,
            publisher_display_name=self.publisher_display_name,
            tags=self.tags,
            skill_count=len(self.skills),
            import_count=self.import_count,
            template_version=self.template_version,
            created_at=self.created_at,
        )

    def to_detail_response(self) -> "MarketplaceAgentDetailResponse":
        return MarketplaceAgentDetailResponse(
            **self.to_summary_response().model_dump(),
            full_description=self.full_description,
            agent_name=self.agent_name,
            agent_architecture=self.agent_architecture,
            agent_provider=self.agent_provider,
            agent_model=self.agent_model,
            allow_model_override=self.allow_model_override,
            agent_persona=self.agent_persona,
            agent_description=self.agent_description,
            skills=self.skills,
            status=self.status,
            source_agent_id=self.source_agent_id,
        )


class MarketplaceAgentSummaryResponse(BaseModel):
    template_id: str
    title: str
    slug: str
    short_description: str
    publisher_display_name: str
    tags: list[str] = Field(default_factory=list)
    skill_count: int
    import_count: int
    template_version: int
    created_at: datetime


class MarketplaceAgentDetailResponse(MarketplaceAgentSummaryResponse):
    full_description: str
    agent_name: str
    agent_architecture: str
    agent_provider: str
    agent_model: str | None = None
    allow_model_override: bool
    agent_persona: str
    agent_description: str | None = None
    skills: list[MarketplaceAgentSkillTemplate] = Field(default_factory=list)
    status: MarketplaceAgentStatus
    source_agent_id: str | None = None


class MarketplaceImportPlanAgent(BaseModel):
    default_name: str
    default_provider: str
    default_model: str | None = None
    allow_model_override: bool = True
    description: str | None = None
    persona_preview: str


class MarketplaceSkillImportForm(BaseModel):
    template_skill_key: str
    skill_id: str
    skill_name: str
    required: bool
    form: Form


class MarketplaceImportPlanResponse(BaseModel):
    template_id: str
    agent: MarketplaceImportPlanAgent
    skill_forms: list[MarketplaceSkillImportForm] = Field(default_factory=list)


class ImportMarketplaceAgentRequest(BaseModel):
    agent_name: str | None = None
    agent_provider: str | None = None
    agent_model: str | None = None
    skill_configs: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ImportedMarketplaceSkillResponse(BaseModel):
    template_skill_key: str
    installed_skill_id: str
    skill_id: str


class ImportMarketplaceAgentResponse(BaseModel):
    agent_id: str
    agent_name: str
    installed_skills: list[ImportedMarketplaceSkillResponse] = Field(default_factory=list)


class PublishMarketplaceAgentRequest(BaseModel):
    agent_id: str
    title: str
    short_description: str
    full_description: str
    tags: list[str] = Field(default_factory=list)
    included_skill_ids: list[str] = Field(default_factory=list)
    status: MarketplaceAgentStatus = MarketplaceAgentStatus.PUBLISHED
    changelog: str | None = None


class PublishMarketplaceAgentResponse(BaseModel):
    template_id: str
    status: MarketplaceAgentStatus
    title: str
    template_version: int


class ArchiveMarketplaceAgentResponse(BaseModel):
    template_id: str
    status: MarketplaceAgentStatus


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "agent"


def agent_to_response(agent: AgentResponse | Any) -> dict[str, Any]:
    if isinstance(agent, AgentResponse):
        return agent.model_dump(mode="json")
    return agent.to_response().model_dump(mode="json")
