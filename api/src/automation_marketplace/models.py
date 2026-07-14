from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from src.automations.models import AutomationNodeType
from src.form_models import Form, FormInput
from src.utils.dynamodb import convert_decimals


class MarketplaceAutomationStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class MarketplaceAutomationSkillTemplate(BaseModel):
    template_skill_key: str
    skill_id: str
    display_name: str | None = None
    description: str | None = None
    required: bool = True
    enabled_on_import: bool = True
    default_config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize(self) -> "MarketplaceAutomationSkillTemplate":
        self.template_skill_key = self.template_skill_key.strip()
        self.skill_id = self.skill_id.strip()
        if not self.template_skill_key:
            raise ValueError("template_skill_key is required")
        if not self.skill_id:
            raise ValueError("skill_id is required")
        return self


class MarketplaceAutomationNodeTemplate(BaseModel):
    node_id: str
    type: AutomationNodeType
    name: str
    description: str | None = None
    position: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class MarketplaceAutomationEdgeTemplate(BaseModel):
    edge_id: str
    source_node_id: str
    target_node_id: str
    label: str = "next"
    condition: str | None = None


class MarketplaceAutomationImportInput(BaseModel):
    input_key: str
    label: str
    description: str | None = None
    required: bool = True
    form_input: FormInput

    @model_validator(mode="after")
    def normalize(self) -> "MarketplaceAutomationImportInput":
        self.input_key = self.input_key.strip()
        if not self.input_key:
            raise ValueError("input_key is required")
        if self.form_input.name != self.input_key:
            self.form_input = self.form_input.model_copy(update={"name": self.input_key})
        return self


class MarketplaceAutomationTemplate(BaseModel):
    template_id: str = Field(default_factory=lambda: f"automation_template_{uuid4()}")
    title: str
    slug: str = ""
    template_version: int = 1
    parent_template_id: str | None = None
    latest_template_id: str | None = None
    changelog: str | None = None
    short_description: str
    full_description: str
    automation_title: str
    automation_description: str | None = None
    nodes: list[MarketplaceAutomationNodeTemplate] = Field(default_factory=list)
    edges: list[MarketplaceAutomationEdgeTemplate] = Field(default_factory=list)
    skills: list[MarketplaceAutomationSkillTemplate] = Field(default_factory=list)
    import_inputs: list[MarketplaceAutomationImportInput] = Field(default_factory=list)
    source_automation_id: str | None = None
    publisher_user_email: str | None = None
    publisher_display_name: str = "InnomightLabs"
    tags: list[str] = Field(default_factory=list)
    status: MarketplaceAutomationStatus = MarketplaceAutomationStatus.DRAFT
    import_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def normalize(self) -> "MarketplaceAutomationTemplate":
        self.title = self.title.strip()
        self.slug = self.slug.strip() or slugify(self.title)
        self.short_description = self.short_description.strip()
        self.full_description = self.full_description.strip()
        self.automation_title = self.automation_title.strip()
        self.automation_description = self.automation_description.strip() if self.automation_description else None
        self.tags = [tag.strip().lower() for tag in self.tags if tag.strip()]
        self.parent_template_id = self.parent_template_id or self.template_id
        self.latest_template_id = self.latest_template_id or self.template_id
        if not self.title:
            raise ValueError("title is required")
        if not self.short_description:
            raise ValueError("short_description is required")
        if not self.full_description:
            raise ValueError("full_description is required")
        if not self.automation_title:
            raise ValueError("automation_title is required")
        return self

    @property
    def pk(self) -> str:
        return "MarketplaceAutomation"

    @property
    def sk(self) -> str:
        return f"Template#{self.template_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return _dynamo_value({
            "pk": self.pk,
            "sk": self.sk,
            "entity_type": "MarketplaceAutomationTemplate",
            "template_id": self.template_id,
            "title": self.title,
            "slug": self.slug,
            "template_version": self.template_version,
            "parent_template_id": self.parent_template_id,
            "latest_template_id": self.latest_template_id,
            "changelog": self.changelog,
            "short_description": self.short_description,
            "full_description": self.full_description,
            "automation_title": self.automation_title,
            "automation_description": self.automation_description,
            "nodes": [node.model_dump(mode="json") for node in self.nodes],
            "edges": [edge.model_dump(mode="json") for edge in self.edges],
            "skills": [skill.model_dump(mode="json") for skill in self.skills],
            "import_inputs": [item.model_dump(mode="json") for item in self.import_inputs],
            "source_automation_id": self.source_automation_id,
            "publisher_user_email": self.publisher_user_email,
            "publisher_display_name": self.publisher_display_name,
            "tags": self.tags,
            "status": self.status.value,
            "import_count": self.import_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        })

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "MarketplaceAutomationTemplate":
        data = convert_decimals(item)
        return cls(
            template_id=data["template_id"],
            title=data["title"],
            slug=data.get("slug", ""),
            template_version=int(data.get("template_version", 1)),
            parent_template_id=data.get("parent_template_id"),
            latest_template_id=data.get("latest_template_id"),
            changelog=data.get("changelog"),
            short_description=data["short_description"],
            full_description=data["full_description"],
            automation_title=data["automation_title"],
            automation_description=data.get("automation_description"),
            nodes=[MarketplaceAutomationNodeTemplate(**node) for node in data.get("nodes", [])],
            edges=[MarketplaceAutomationEdgeTemplate(**edge) for edge in data.get("edges", [])],
            skills=[MarketplaceAutomationSkillTemplate(**skill) for skill in data.get("skills", [])],
            import_inputs=[MarketplaceAutomationImportInput(**item) for item in data.get("import_inputs", [])],
            source_automation_id=data.get("source_automation_id"),
            publisher_user_email=data.get("publisher_user_email"),
            publisher_display_name=data.get("publisher_display_name", "InnomightLabs"),
            tags=data.get("tags", []) or [],
            status=MarketplaceAutomationStatus(data.get("status", MarketplaceAutomationStatus.DRAFT.value)),
            import_count=int(data.get("import_count", 0)),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
        )

    def to_summary_response(self) -> "MarketplaceAutomationSummaryResponse":
        return MarketplaceAutomationSummaryResponse(
            template_id=self.template_id,
            title=self.title,
            slug=self.slug,
            short_description=self.short_description,
            publisher_display_name=self.publisher_display_name,
            tags=self.tags,
            node_count=len(self.nodes),
            edge_count=len(self.edges),
            skill_count=len(self.skills),
            import_count=self.import_count,
            template_version=self.template_version,
            created_at=self.created_at,
        )

    def to_detail_response(self) -> "MarketplaceAutomationDetailResponse":
        return MarketplaceAutomationDetailResponse(
            **self.to_summary_response().model_dump(),
            full_description=self.full_description,
            automation_title=self.automation_title,
            automation_description=self.automation_description,
            nodes=self.nodes,
            edges=self.edges,
            skills=self.skills,
            import_inputs=self.import_inputs,
            status=self.status,
            source_automation_id=self.source_automation_id,
        )


class MarketplaceAutomationSummaryResponse(BaseModel):
    template_id: str
    title: str
    slug: str
    short_description: str
    publisher_display_name: str
    tags: list[str] = Field(default_factory=list)
    node_count: int
    edge_count: int
    skill_count: int
    import_count: int
    template_version: int
    created_at: datetime


class MarketplaceAutomationDetailResponse(MarketplaceAutomationSummaryResponse):
    full_description: str
    automation_title: str
    automation_description: str | None = None
    nodes: list[MarketplaceAutomationNodeTemplate] = Field(default_factory=list)
    edges: list[MarketplaceAutomationEdgeTemplate] = Field(default_factory=list)
    skills: list[MarketplaceAutomationSkillTemplate] = Field(default_factory=list)
    import_inputs: list[MarketplaceAutomationImportInput] = Field(default_factory=list)
    status: MarketplaceAutomationStatus
    source_automation_id: str | None = None


class MarketplaceAutomationImportPlanInfo(BaseModel):
    default_title: str
    description: str | None = None
    node_count: int
    edge_count: int


class MarketplaceAutomationSkillImportForm(BaseModel):
    template_skill_key: str
    skill_id: str
    skill_name: str
    required: bool
    form: Form


class MarketplaceAutomationImportPlanResponse(BaseModel):
    template_id: str
    automation: MarketplaceAutomationImportPlanInfo
    skill_forms: list[MarketplaceAutomationSkillImportForm] = Field(default_factory=list)
    input_form: Form


IMPORT_SESSION_TTL_MINUTES = 30


class MarketplaceAutomationImportSession(BaseModel):
    session_id: str = Field(default_factory=lambda: f"automation_import_session_{uuid4().hex}")
    template_id: str
    owner_email: str
    title: str | None = None
    description: str | None = None
    skill_configs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    import_inputs: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=IMPORT_SESSION_TTL_MINUTES)
    )
    ttl: int = Field(
        default_factory=lambda: int(
            (datetime.now(timezone.utc) + timedelta(minutes=IMPORT_SESSION_TTL_MINUTES)).timestamp()
        )
    )

    @property
    def pk(self) -> str:
        return f"User#{self.owner_email}"

    @property
    def sk(self) -> str:
        return f"AutomationMarketplaceImportSession#{self.session_id}"

    def is_expired(self) -> bool:
        return self.expires_at <= datetime.now(timezone.utc)

    def refresh_expiry(self) -> None:
        self.updated_at = datetime.now(timezone.utc)
        self.expires_at = datetime.now(timezone.utc) + timedelta(minutes=IMPORT_SESSION_TTL_MINUTES)
        self.ttl = int(self.expires_at.timestamp())

    def to_dynamo_item(self) -> dict[str, Any]:
        return _dynamo_value({
            "pk": self.pk,
            "sk": self.sk,
            "entity_type": "MarketplaceAutomationImportSession",
            "session_id": self.session_id,
            "template_id": self.template_id,
            "owner_email": self.owner_email,
            "title": self.title,
            "description": self.description,
            "skill_configs": self.skill_configs,
            "import_inputs": self.import_inputs,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "expires_at": self.expires_at.isoformat(),
            "ttl": self.ttl,
        })

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "MarketplaceAutomationImportSession":
        data = convert_decimals(item)
        return cls(
            session_id=data["session_id"],
            template_id=data["template_id"],
            owner_email=data["owner_email"],
            title=data.get("title"),
            description=data.get("description"),
            skill_configs=data.get("skill_configs", {}) or {},
            import_inputs=data.get("import_inputs", {}) or {},
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
            expires_at=datetime.fromisoformat(data["expires_at"]),
            ttl=int(data["ttl"]),
        )


class SaveMarketplaceAutomationImportSessionRequest(BaseModel):
    session_id: str | None = None
    title: str | None = None
    description: str | None = None
    skill_configs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    import_inputs: dict[str, Any] = Field(default_factory=dict)


class MarketplaceAutomationImportSessionResponse(BaseModel):
    session_id: str
    template_id: str
    title: str | None = None
    description: str | None = None
    skill_configs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    import_inputs: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime


class ImportMarketplaceAutomationRequest(BaseModel):
    session_id: str | None = None
    title: str | None = None
    description: str | None = None
    skill_configs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    import_inputs: dict[str, Any] = Field(default_factory=dict)


class ImportedMarketplaceAutomationSkillResponse(BaseModel):
    template_skill_key: str
    installed_skill_id: str
    skill_id: str


class ImportMarketplaceAutomationResponse(BaseModel):
    automation_id: str
    title: str
    installed_skills: list[ImportedMarketplaceAutomationSkillResponse] = Field(default_factory=list)
    node_count: int
    edge_count: int


class PublishMarketplaceAutomationRequest(BaseModel):
    automation_id: str
    title: str
    short_description: str
    full_description: str
    tags: list[str] = Field(default_factory=list)
    included_skill_ids: list[str] = Field(default_factory=list)
    included_node_ids: list[str] = Field(default_factory=list)
    included_edge_ids: list[str] = Field(default_factory=list)
    import_inputs: list[MarketplaceAutomationImportInput] = Field(default_factory=list)
    status: MarketplaceAutomationStatus = MarketplaceAutomationStatus.PUBLISHED
    changelog: str | None = None


class PublishMarketplaceAutomationResponse(BaseModel):
    template_id: str
    status: MarketplaceAutomationStatus
    title: str
    template_version: int


class ArchiveMarketplaceAutomationResponse(BaseModel):
    template_id: str
    status: MarketplaceAutomationStatus


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "automation"


def _dynamo_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_dynamo_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _dynamo_value(item) for key, item in value.items()}
    return value
