from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class A2ATaskState(str, Enum):
    SUBMITTED = "TASK_STATE_SUBMITTED"
    WORKING = "TASK_STATE_WORKING"
    INPUT_REQUIRED = "TASK_STATE_INPUT_REQUIRED"
    COMPLETED = "TASK_STATE_COMPLETED"
    FAILED = "TASK_STATE_FAILED"
    CANCELED = "TASK_STATE_CANCELED"
    REJECTED = "TASK_STATE_REJECTED"


class A2AMessageRole(str, Enum):
    USER = "ROLE_USER"
    AGENT = "ROLE_AGENT"


class A2APartKind(str, Enum):
    TEXT = "text"


class A2AErrorCode(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    NOT_FOUND = "NOT_FOUND"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class A2ATextPart(BaseModel):
    kind: A2APartKind = A2APartKind.TEXT
    text: str = Field(min_length=1)


class A2AMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message_id: str = Field(default_factory=lambda: str(uuid4()), alias="messageId")
    role: A2AMessageRole
    parts: list[A2ATextPart]
    task_id: str | None = Field(default=None, alias="taskId")
    context_id: str | None = Field(default=None, alias="contextId")

    @field_validator("parts")
    @classmethod
    def validate_parts(cls, value: list[A2ATextPart]) -> list[A2ATextPart]:
        if not value:
            raise ValueError("At least one text part is required")
        if len(value) > 16:
            raise ValueError("Maximum 16 text parts are allowed")
        total_length = sum(len(part.text) for part in value)
        if total_length > 32000:
            raise ValueError("Message text exceeds 32000 characters")
        return value


class A2AMessageConfiguration(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    accepted_output_modes: list[str] | None = Field(default=None, alias="acceptedOutputModes")


class A2AMessageSendRequest(BaseModel):
    message: A2AMessage
    configuration: A2AMessageConfiguration | None = None


class A2ATaskStatus(BaseModel):
    state: A2ATaskState
    message: A2AMessage | None = None


class A2ATask(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: str = Field(default_factory=lambda: str(uuid4()), alias="id")
    context_id: str = Field(alias="contextId")
    agent_id: str = Field(alias="agentId")
    owner_email: str = Field(alias="ownerEmail")
    client_key_id: str = Field(alias="clientKeyId")
    conversation_id: str = Field(alias="conversationId")
    status: A2ATaskStatus
    history: list[A2AMessage] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), alias="createdAt")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), alias="updatedAt")
    ttl: int | None = None

    @property
    def pk(self) -> str:
        return f"A2A#Agent#{self.agent_id}"

    @property
    def sk(self) -> str:
        return f"Task#{self.task_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "gsi2_pk": f"A2ATask#{self.task_id}",
            "gsi2_sk": f"Agent#{self.agent_id}",
            "entity_type": "A2ATask",
            "task_id": self.task_id,
            "context_id": self.context_id,
            "agent_id": self.agent_id,
            "owner_email": self.owner_email,
            "client_key_id": self.client_key_id,
            "conversation_id": self.conversation_id,
            "status": self.status.model_dump(mode="json", by_alias=True, exclude_none=True),
            "history": [
                message.model_dump(mode="json", by_alias=True, exclude_none=True)
                for message in self.history
            ],
            "artifacts": self.artifacts,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "ttl": self.ttl,
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "A2ATask":
        return cls(
            id=item["task_id"],
            contextId=item["context_id"],
            agentId=item["agent_id"],
            ownerEmail=item["owner_email"],
            clientKeyId=item["client_key_id"],
            conversationId=item["conversation_id"],
            status=A2ATaskStatus(**item["status"]),
            history=[A2AMessage(**message) for message in item.get("history", [])],
            artifacts=item.get("artifacts", []),
            createdAt=datetime.fromisoformat(item["created_at"]),
            updatedAt=datetime.fromisoformat(item["updated_at"]),
            ttl=item.get("ttl"),
        )


class A2ATaskResponse(BaseModel):
    task: A2ATask


class A2ATaskListResponse(BaseModel):
    items: list[A2ATask] = Field(default_factory=list)


class A2ATaskStatusUpdateEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: str = Field(alias="taskId")
    context_id: str = Field(alias="contextId")
    status: A2ATaskStatus
    final: bool = False


class A2AErrorResponse(BaseModel):
    code: A2AErrorCode
    message: str


class A2AAgentSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    agent_id: str = Field(alias="id")
    name: str
    description: str | None = None
    agent_card_url: str = Field(alias="agentCardUrl")
    agent_card: "A2AAgentCard" = Field(alias="agentCard")


class A2AAgentListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[A2AAgentSummary] = Field(default_factory=list)
    next_cursor: str | None = Field(default=None, alias="nextCursor")


class A2AAgentProvider(BaseModel):
    organization: str
    url: str | None = None


class A2AAgentCapabilities(BaseModel):
    streaming: bool = True
    pushNotifications: bool = False
    extendedAgentCard: bool = False


class A2AAgentInterface(BaseModel):
    url: str
    protocolBinding: str
    protocolVersion: str = "1.0"
    tenant: str | None = None


class A2AApiKeySecurityScheme(BaseModel):
    location: str
    name: str
    description: str | None = None


class A2AHttpAuthSecurityScheme(BaseModel):
    scheme: str
    bearerFormat: str | None = None
    description: str | None = None


class A2ASecurityScheme(BaseModel):
    apiKeySecurityScheme: A2AApiKeySecurityScheme | None = None
    httpAuthSecurityScheme: A2AHttpAuthSecurityScheme | None = None


class A2AStringList(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    values: list[str] = Field(default_factory=list, alias="list")


class A2ASecurityRequirement(BaseModel):
    schemes: dict[str, A2AStringList]


class A2ASkill(BaseModel):
    id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)


class A2AAgentCard(BaseModel):
    name: str
    description: str
    supportedInterfaces: list[A2AAgentInterface]
    provider: A2AAgentProvider | None = None
    version: str
    documentationUrl: str | None = None
    capabilities: A2AAgentCapabilities
    securitySchemes: dict[str, A2ASecurityScheme]
    securityRequirements: list[A2ASecurityRequirement]
    defaultInputModes: list[str]
    defaultOutputModes: list[str]
    skills: list[A2ASkill]
