"""DynamoDB-backed models for Dream runs and their audit trail."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from src.automations.models import dynamo_item
from src.utils.dynamodb import convert_decimals


class DreamSettings(BaseModel):
    user_email: str
    enabled: bool = False
    provider_name: str | None = None
    model_name: str | None = None
    cron_expression: str = "0 3 * * *"
    timezone: str = "UTC"
    soft_sessions_per_run: int = 25
    soft_chunks_per_run: int = 120
    soft_actions_per_run: int = 40
    min_confidence: float = 0.75
    backfill_days: int = 30
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_model_when_enabled(self) -> "DreamSettings":
        if self.enabled and (not self.provider_name or not self.model_name):
            raise ValueError("provider_name and model_name are required when dreaming is enabled")
        return self

    @property
    def pk(self) -> str:
        return f"User#{self.user_email}"

    @property
    def sk(self) -> str:
        return "DreamSettings"

    def to_dynamo_item(self) -> dict[str, Any]:
        return dynamo_item(
            {
                "pk": self.pk,
                "sk": self.sk,
                "entity_type": "DreamSettings",
                **self.model_dump(mode="json"),
            }
        )

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "DreamSettings":
        return cls(**convert_decimals(item))


class DreamSettingsRequest(BaseModel):
    enabled: bool = False
    provider_name: str | None = None
    model_name: str | None = None
    cron_expression: str = "0 3 * * *"
    timezone: str = "UTC"
    soft_sessions_per_run: int = Field(default=25, gt=0)
    soft_chunks_per_run: int = Field(default=120, gt=0)
    soft_actions_per_run: int = Field(default=40, gt=0)
    min_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    backfill_days: int = Field(default=30, gt=0)

    @model_validator(mode="after")
    def validate_model_when_enabled(self) -> "DreamSettingsRequest":
        if self.enabled and (not self.provider_name or not self.model_name):
            raise ValueError("provider_name and model_name are required when dreaming is enabled")
        return self


class DreamCursor(BaseModel):
    agent_id: str
    user_id: str
    last_session_ended_at: datetime | None = None
    last_run_id: str | None = None
    sessions_dreamed: int = 0
    backfill_completed: bool = False
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def pk(self) -> str:
        return f"Agent#{self.agent_id}#User#{self.user_id}"

    @property
    def sk(self) -> str:
        return "DreamCursor"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "entity_type": "DreamCursor",
            **self.model_dump(mode="json"),
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "DreamCursor":
        return cls(**item)


class DreamRunStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class DreamRun(BaseModel):
    run_id: str
    agent_id: str
    user_id: str
    owner_email: str
    status: DreamRunStatus = DreamRunStatus.RUNNING
    mode: Literal["backfill", "daily", "manual"] = "daily"
    window_start: datetime | None = None
    window_end: datetime | None = None
    sessions_considered: int = 0
    sessions_dreamed: int = 0
    chunks_planned: int = 0
    chunks_skipped_empty: int = 0
    sessions_remaining: int = 0
    budget_overshoot_chunks: int = 0
    budget_overshoot_actions: int = 0
    longest_session_chunks: int = 0
    candidates_extracted: int = 0
    actions_proposed: int = 0
    actions_executed: int = 0
    actions_skipped: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    @property
    def pk(self) -> str:
        return f"Agent#{self.agent_id}#User#{self.user_id}"

    @property
    def sk(self) -> str:
        return f"DreamRun#{self.started_at.isoformat()}#{self.run_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "entity_type": "DreamRun",
            **self.model_dump(mode="json"),
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "DreamRun":
        return cls(**item)


class DreamActionOutcome(str, Enum):
    EXECUTED = "executed"
    SKIPPED_LOW_CONFIDENCE = "skipped_low_confidence"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    SKIPPED_STALE_LINE = "skipped_stale_line"
    SKIPPED_REDACTED = "skipped_redacted"
    SKIPPED_UNKNOWN_BLOCK = "skipped_unknown_block"
    FAILED = "failed"


class DreamActionType(str, Enum):
    APPEND_CORE = "append_core"
    REPLACE_CORE = "replace_core"
    DELETE_CORE = "delete_core"
    INSERT_ARCHIVAL = "insert_archival"
    NO_OP = "no_op"


class DreamAction(BaseModel):
    type: DreamActionType
    block_name: str = ""
    line_number: int | None = None
    content: str = ""
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class DreamPlan(BaseModel):
    actions: list[DreamAction] = Field(default_factory=list)
    session_summary: str = ""


class DreamActionLog(BaseModel):
    run_id: str
    index: int
    action_type: DreamActionType
    block_name: str = ""
    line_number: int | None = None
    content_preview: str = ""
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    outcome: DreamActionOutcome
    detail: str = ""
    session_ref: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ttl: int = Field(default_factory=lambda: int((datetime.now(timezone.utc) + timedelta(days=90)).timestamp()))

    @field_validator("content_preview")
    @classmethod
    def limit_content_preview(cls, value: str) -> str:
        return value[:200]

    @property
    def pk(self) -> str:
        return f"DreamRun#{self.run_id}"

    @property
    def sk(self) -> str:
        return f"Action#{self.index:04d}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return dynamo_item(
            {
                "pk": self.pk,
                "sk": self.sk,
                "entity_type": "DreamActionLog",
                **self.model_dump(mode="json"),
            }
        )

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "DreamActionLog":
        return cls(**convert_decimals(item))
