from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from src.utils.dynamodb import convert_decimals

TOOL_JOB_TTL_DAYS = 7


class ToolJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ToolJob(BaseModel):
    job_id: str = Field(default_factory=lambda: f"tooljob_{uuid4().hex}")
    owner_email: str
    actor_email: str
    actor_id: str
    agent_id: str | None = None
    conversation_id: str | None = None
    user_message_id: str | None = None
    automation_id: str | None = None
    automation_run_id: str | None = None
    automation_node_id: str | None = None
    tool_name: str
    skill_id: str | None = None
    installed_skill_id: str | None = None
    action: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    status: ToolJobStatus = ToolJobStatus.QUEUED
    progress_message: str | None = None
    result: Any | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    ttl: int = Field(
        default_factory=lambda: int(
            (datetime.now(timezone.utc) + timedelta(days=TOOL_JOB_TTL_DAYS)).timestamp()
        )
    )

    @property
    def pk(self) -> str:
        return f"User#{self.owner_email}"

    @property
    def sk(self) -> str:
        return f"ToolJob#{self.job_id}"

    @property
    def gsi2_pk(self) -> str:
        return f"ToolJob#{self.job_id}"

    @property
    def gsi2_sk(self) -> str:
        return f"ToolJob#{self.job_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        payload = _convert_floats_to_decimals(self.model_dump(mode="json"))
        payload.update(
            {
                "pk": self.pk,
                "sk": self.sk,
                "gsi2_pk": self.gsi2_pk,
                "gsi2_sk": self.gsi2_sk,
                "entity_type": "ToolJob",
            }
        )
        return payload

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "ToolJob":
        payload = convert_decimals(dict(item))
        for key in ("pk", "sk", "gsi2_pk", "gsi2_sk", "entity_type"):
            payload.pop(key, None)
        return cls(**payload)

    def to_status_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.status != ToolJobStatus.FAILED,
            "async": True,
            "job_id": self.job_id,
            "status": self.status.value,
        }
        if self.progress_message:
            payload["progress_message"] = self.progress_message
        if self.started_at:
            payload["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            payload["completed_at"] = self.completed_at.isoformat()
        if self.status == ToolJobStatus.SUCCEEDED:
            payload["result"] = self.result
        if self.status == ToolJobStatus.FAILED:
            payload["error"] = self.error or "Tool job failed"
        return payload

    def to_start_payload(self) -> dict[str, Any]:
        return {
            "ok": True,
            "async": True,
            "job_id": self.job_id,
            "status": self.status.value,
            "message": f"Started {self.action or self.tool_name}. The runtime will keep checking this job until it succeeds or fails.",
            "check_tool": "check_tool_job",
            "wait_tool": "wait",
        }


def _convert_floats_to_decimals(value: Any) -> Any:
    from decimal import Decimal

    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_convert_floats_to_decimals(item) for item in value]
    if isinstance(value, dict):
        return {key: _convert_floats_to_decimals(item) for key, item in value.items()}
    return value
