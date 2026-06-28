"""Automation domain models and API schemas."""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Optional, cast
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from src.utils.dynamodb import convert_decimals


class AutomationStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"
    DELETED = "deleted"


class AutomationNodeType(str, Enum):
    START = "start"
    ACTION = "action"
    CONDITION = "condition"
    FINAL = "final"


class AutomationActionType(str, Enum):
    SKILL_ACTION = "skill_action"
    INVOKE_AGENT = "invoke_agent"
    SEND_EMAIL = "send_email"
    WEBHOOK_CALL = "webhook_call"


class AutomationTriggerType(str, Enum):
    MANUAL = "manual"
    WEBHOOK = "webhook"
    SCHEDULE = "schedule"


class AutomationRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AutomationNodeRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


def convert_floats_to_decimals(value: Any) -> Any:
    """Recursively convert Python floats before writing to DynamoDB."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [convert_floats_to_decimals(item) for item in value]
    if isinstance(value, dict):
        return {key: convert_floats_to_decimals(item) for key, item in value.items()}
    return value


def dynamo_item(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], convert_floats_to_decimals(value))


class InvokeAgentActionConfig(BaseModel):
    action_type: AutomationActionType = AutomationActionType.INVOKE_AGENT
    agent_id: str
    prompt_template: str
    input: dict[str, Any] = Field(default_factory=dict)

    @field_validator("action_type")
    @classmethod
    def validate_action_type(cls, value: AutomationActionType) -> AutomationActionType:
        if value != AutomationActionType.INVOKE_AGENT:
            raise ValueError("InvokeAgentActionConfig requires action_type='invoke_agent'")
        return value


class SkillActionConfig(BaseModel):
    action_type: AutomationActionType = AutomationActionType.SKILL_ACTION
    skill_id: Optional[str] = None
    installed_skill_id: Optional[str] = None
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    async_: bool = Field(default=False, alias="async")

    @field_validator("action_type")
    @classmethod
    def validate_action_type(cls, value: AutomationActionType) -> AutomationActionType:
        if value != AutomationActionType.SKILL_ACTION:
            raise ValueError("SkillActionConfig requires action_type='skill_action'")
        return value

    @model_validator(mode="after")
    def validate_skill_reference(self) -> "SkillActionConfig":
        if not self.installed_skill_id and not self.skill_id:
            raise ValueError("SkillActionConfig requires installed_skill_id or skill_id")
        return self


class ConditionNodeConfig(BaseModel):
    expression: str
    true_label: str = "true"
    false_label: str = "false"


class AutomationResponse(BaseModel):
    automation_id: str
    title: str
    description: Optional[str] = None
    status: AutomationStatus
    version: int = 1
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class AutomationNodeResponse(BaseModel):
    node_id: str
    automation_id: str
    type: AutomationNodeType
    name: str
    description: Optional[str] = None
    position: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: Optional[datetime] = None


class AutomationEdgeResponse(BaseModel):
    edge_id: str
    automation_id: str
    source_node_id: str
    target_node_id: str
    label: str = "next"
    condition: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class AutomationTriggerResponse(BaseModel):
    trigger_id: str
    automation_id: str
    type: AutomationTriggerType
    name: str
    enabled: bool = False
    entry_node_id: str
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: Optional[datetime] = None


class AutomationGraphResponse(BaseModel):
    automation: AutomationResponse
    nodes: list[AutomationNodeResponse] = Field(default_factory=list)
    edges: list[AutomationEdgeResponse] = Field(default_factory=list)
    triggers: list[AutomationTriggerResponse] = Field(default_factory=list)


class AutomationRunResponse(BaseModel):
    run_id: str
    automation_id: str
    trigger_id: Optional[str] = None
    conversation_id: Optional[str] = None
    status: AutomationRunStatus
    error: Optional[str] = None
    created_by: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class AutomationRunNodeResultResponse(BaseModel):
    result_id: str
    run_id: str
    automation_id: str
    node_id: str
    status: AutomationNodeRunStatus
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    message_ids: dict[str, str] = Field(default_factory=dict)
    started_at: datetime
    completed_at: Optional[datetime] = None


class AutomationRunDetailResponse(BaseModel):
    run: AutomationRunResponse
    context: dict[str, Any] = Field(default_factory=dict)
    node_results: list[AutomationRunNodeResultResponse] = Field(default_factory=list)


class AutomationSkillConnectorResponse(BaseModel):
    connector_id: str
    provider_name: str
    required: bool = True
    connected: bool = False
    connect_path: Optional[str] = None


class AutomationSkillResponse(BaseModel):
    installed_skill_id: str
    skill_id: str
    namespace: str
    name: str
    description: str
    enabled: bool
    enabled_at: datetime
    updated_at: Optional[datetime] = None
    config: dict[str, Any] = Field(default_factory=dict)
    connectors: list[AutomationSkillConnectorResponse] = Field(default_factory=list)


class AutomationActionCatalogItemResponse(BaseModel):
    action_type: AutomationActionType = AutomationActionType.SKILL_ACTION
    skill_id: str
    installed_skill_id: Optional[str] = None
    skill_name: str
    action: str
    label: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    action_form: Optional[dict[str, Any]] = None
    available: bool = True
    configured: bool = True
    enabled: bool = True
    disabled_reason: Optional[str] = None
    install_schema: Optional[dict[str, Any]] = None
    connectors: list[AutomationSkillConnectorResponse] = Field(default_factory=list)


class AutomationActionCatalogResponse(BaseModel):
    actions: list[AutomationActionCatalogItemResponse] = Field(default_factory=list)


class CreateAutomationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    status: AutomationStatus = AutomationStatus.DRAFT


class UpdateAutomationRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    status: Optional[AutomationStatus] = None


class CreateAutomationNodeRequest(BaseModel):
    node_id: Optional[str] = None
    type: AutomationNodeType
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    position: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class UpdateAutomationNodeRequest(BaseModel):
    type: Optional[AutomationNodeType] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    position: Optional[dict[str, Any]] = None
    config: Optional[dict[str, Any]] = None


class CreateAutomationEdgeRequest(BaseModel):
    edge_id: Optional[str] = None
    source_node_id: str
    target_node_id: str
    label: str = Field(default="next", min_length=1, max_length=50)
    condition: Optional[str] = Field(default=None, max_length=1000)


class UpdateAutomationEdgeRequest(BaseModel):
    source_node_id: Optional[str] = None
    target_node_id: Optional[str] = None
    label: Optional[str] = Field(default=None, min_length=1, max_length=50)
    condition: Optional[str] = Field(default=None, max_length=1000)


class CreateAutomationTriggerRequest(BaseModel):
    trigger_id: Optional[str] = None
    type: AutomationTriggerType
    name: str = Field(min_length=1, max_length=200)
    enabled: bool = False
    entry_node_id: str
    config: dict[str, Any] = Field(default_factory=dict)


class UpdateAutomationTriggerRequest(BaseModel):
    type: Optional[AutomationTriggerType] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    enabled: Optional[bool] = None
    entry_node_id: Optional[str] = None
    config: Optional[dict[str, Any]] = None


class SaveAutomationGraphRequest(BaseModel):
    nodes: list[CreateAutomationNodeRequest] = Field(default_factory=list)
    edges: list[CreateAutomationEdgeRequest] = Field(default_factory=list)
    triggers: list[CreateAutomationTriggerRequest] = Field(default_factory=list)


class StartAutomationRunRequest(BaseModel):
    trigger_id: Optional[str] = None
    input: dict[str, Any] = Field(default_factory=dict)


class EnableAutomationSkillRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class UpdateAutomationSkillRequest(BaseModel):
    enabled: Optional[bool] = None
    config: Optional[dict[str, Any]] = None


class Automation(BaseModel):
    automation_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: Optional[str] = None
    status: AutomationStatus = AutomationStatus.DRAFT
    created_by: str
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"User#{self.created_by}"

    @property
    def sk(self) -> str:
        return f"Automation#{self.automation_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "automation_id": self.automation_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "created_by": self.created_by,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "entity_type": "Automation",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "Automation":
        item = convert_decimals(item)
        return cls(
            automation_id=item["automation_id"],
            title=item["title"],
            description=item.get("description"),
            status=AutomationStatus(item.get("status", AutomationStatus.DRAFT.value)),
            created_by=item["created_by"],
            version=int(item.get("version", 1)),
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )

    def to_response(self) -> AutomationResponse:
        return AutomationResponse(**self.model_dump())


class AutomationNode(BaseModel):
    node_id: str = Field(default_factory=lambda: str(uuid4()))
    automation_id: str
    type: AutomationNodeType
    name: str
    description: Optional[str] = None
    position: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"Automation#{self.automation_id}"

    @property
    def sk(self) -> str:
        return f"Node#{self.node_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return dynamo_item({
            "pk": self.pk,
            "sk": self.sk,
            "node_id": self.node_id,
            "automation_id": self.automation_id,
            "type": self.type.value,
            "name": self.name,
            "description": self.description,
            "position": self.position,
            "config": self.config,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "entity_type": "AutomationNode",
        })

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "AutomationNode":
        item = convert_decimals(item)
        return cls(
            node_id=item["node_id"],
            automation_id=item["automation_id"],
            type=AutomationNodeType(item["type"]),
            name=item["name"],
            description=item.get("description"),
            position=item.get("position") or {},
            config=item.get("config") or {},
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )

    def to_response(self) -> AutomationNodeResponse:
        return AutomationNodeResponse(**self.model_dump())


class AutomationEdge(BaseModel):
    edge_id: str = Field(default_factory=lambda: str(uuid4()))
    automation_id: str
    source_node_id: str
    target_node_id: str
    label: str = "next"
    condition: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"Automation#{self.automation_id}"

    @property
    def sk(self) -> str:
        return f"Edge#{self.edge_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "edge_id": self.edge_id,
            "automation_id": self.automation_id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "label": self.label,
            "condition": self.condition,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "entity_type": "AutomationEdge",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "AutomationEdge":
        item = convert_decimals(item)
        return cls(
            edge_id=item["edge_id"],
            automation_id=item["automation_id"],
            source_node_id=item["source_node_id"],
            target_node_id=item["target_node_id"],
            label=item.get("label", "next"),
            condition=item.get("condition"),
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )

    def to_response(self) -> AutomationEdgeResponse:
        return AutomationEdgeResponse(**self.model_dump())


class AutomationTrigger(BaseModel):
    trigger_id: str = Field(default_factory=lambda: str(uuid4()))
    automation_id: str
    type: AutomationTriggerType
    name: str
    enabled: bool = False
    entry_node_id: str
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"Automation#{self.automation_id}"

    @property
    def sk(self) -> str:
        return f"Trigger#{self.trigger_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        item = dynamo_item({
            "pk": self.pk,
            "sk": self.sk,
            "trigger_id": self.trigger_id,
            "automation_id": self.automation_id,
            "type": self.type.value,
            "name": self.name,
            "enabled": self.enabled,
            "entry_node_id": self.entry_node_id,
            "config": self.config,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "entity_type": "AutomationTrigger",
        })
        token_hash = self.config.get("token_hash")
        if self.type == AutomationTriggerType.WEBHOOK and token_hash:
            item["gsi2_pk"] = f"WebhookTrigger#{token_hash}"
            item["gsi2_sk"] = f"Automation#{self.automation_id}#Trigger#{self.trigger_id}"
        return item

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "AutomationTrigger":
        item = convert_decimals(item)
        return cls(
            trigger_id=item["trigger_id"],
            automation_id=item["automation_id"],
            type=AutomationTriggerType(item["type"]),
            name=item["name"],
            enabled=bool(item.get("enabled", False)),
            entry_node_id=item["entry_node_id"],
            config=item.get("config") or {},
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )

    def to_response(self) -> AutomationTriggerResponse:
        return AutomationTriggerResponse(**self.model_dump())


class AutomationSkill(BaseModel):
    automation_id: str
    installed_skill_id: str = ""
    skill_id: str
    namespace: str
    skill_name: str
    skill_description: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    encrypted_secrets: str = ""
    secret_fields: list[str] = Field(default_factory=list)
    enabled_by: str
    enabled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"Automation#{self.automation_id}"

    @property
    def sk(self) -> str:
        return f"Skill#{self.installed_skill_id or self.skill_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return dynamo_item({
            "pk": self.pk,
            "sk": self.sk,
            "entity_type": "AutomationSkill",
            "automation_id": self.automation_id,
            "installed_skill_id": self.installed_skill_id or self.skill_id,
            "skill_id": self.skill_id,
            "namespace": self.namespace,
            "skill_name": self.skill_name,
            "skill_description": self.skill_description,
            "enabled": self.enabled,
            "config": self.config,
            "encrypted_secrets": self.encrypted_secrets,
            "secret_fields": self.secret_fields,
            "enabled_by": self.enabled_by,
            "enabled_at": self.enabled_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        })

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "AutomationSkill":
        item = convert_decimals(item)
        return cls(
            automation_id=item["automation_id"],
            installed_skill_id=item.get("installed_skill_id", item["skill_id"]),
            skill_id=item["skill_id"],
            namespace=item.get("namespace", ""),
            skill_name=item.get("skill_name", item["skill_id"]),
            skill_description=item.get("skill_description", ""),
            enabled=bool(item.get("enabled", True)),
            config=item.get("config") or {},
            encrypted_secrets=item.get("encrypted_secrets", ""),
            secret_fields=item.get("secret_fields") or [],
            enabled_by=item.get("enabled_by", ""),
            enabled_at=datetime.fromisoformat(item["enabled_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )


class AutomationRun(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    automation_id: str
    trigger_id: Optional[str] = None
    conversation_id: Optional[str] = None
    status: AutomationRunStatus = AutomationRunStatus.PENDING
    context: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"Automation#{self.automation_id}"

    @property
    def sk(self) -> str:
        return f"Run#{self.created_at.isoformat()}#{self.run_id}"

    @property
    def owner_pk(self) -> str:
        return f"User#{self.created_by}"

    @property
    def owner_sk(self) -> str:
        return f"AutomationRun#{self.run_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return dynamo_item({
            "pk": self.pk,
            "sk": self.sk,
            "run_id": self.run_id,
            "automation_id": self.automation_id,
            "trigger_id": self.trigger_id,
            "conversation_id": self.conversation_id,
            "status": self.status.value,
            "context": self.context,
            "error": self.error,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "entity_type": "AutomationRun",
        })

    def to_owner_lookup_item(self) -> dict[str, Any]:
        item = self.to_dynamo_item()
        item.update(
            {
                "pk": self.owner_pk,
                "sk": self.owner_sk,
                "entity_type": "AutomationRunLookup",
            }
        )
        return item

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "AutomationRun":
        item = convert_decimals(item)
        return cls(
            run_id=item["run_id"],
            automation_id=item["automation_id"],
            trigger_id=item.get("trigger_id"),
            conversation_id=item.get("conversation_id"),
            status=AutomationRunStatus(item.get("status", AutomationRunStatus.PENDING.value)),
            context=item.get("context") or {},
            error=item.get("error"),
            created_by=item["created_by"],
            created_at=datetime.fromisoformat(item["created_at"]),
            started_at=datetime.fromisoformat(item["started_at"]) if item.get("started_at") else None,
            completed_at=datetime.fromisoformat(item["completed_at"]) if item.get("completed_at") else None,
        )

    def to_response(self) -> AutomationRunResponse:
        data = self.model_dump(exclude={"context"})
        return AutomationRunResponse(**data)


class AutomationRunNodeResult(BaseModel):
    result_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    automation_id: str
    node_id: str
    status: AutomationNodeRunStatus = AutomationNodeRunStatus.PENDING
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    message_ids: dict[str, str] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"AutomationRun#{self.run_id}"

    @property
    def sk(self) -> str:
        return f"NodeResult#{self.started_at.isoformat()}#{self.node_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return dynamo_item({
            "pk": self.pk,
            "sk": self.sk,
            "result_id": self.result_id,
            "run_id": self.run_id,
            "automation_id": self.automation_id,
            "node_id": self.node_id,
            "status": self.status.value,
            "input": self.input,
            "output": self.output,
            "error": self.error,
            "message_ids": self.message_ids,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "entity_type": "AutomationRunNodeResult",
        })

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "AutomationRunNodeResult":
        item = convert_decimals(item)
        return cls(
            result_id=item["result_id"],
            run_id=item["run_id"],
            automation_id=item["automation_id"],
            node_id=item["node_id"],
            status=AutomationNodeRunStatus(
                item.get("status", AutomationNodeRunStatus.PENDING.value)
            ),
            input=item.get("input") or {},
            output=item.get("output") or {},
            error=item.get("error"),
            message_ids=item.get("message_ids") or {},
            started_at=datetime.fromisoformat(item["started_at"]),
            completed_at=datetime.fromisoformat(item["completed_at"]) if item.get("completed_at") else None,
        )

    def to_response(self) -> AutomationRunNodeResultResponse:
        return AutomationRunNodeResultResponse(**self.model_dump())
