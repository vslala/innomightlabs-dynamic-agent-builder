"""Scheduler domain models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from src.automations.models import convert_floats_to_decimals
from src.utils.dynamodb import convert_decimals


class ScheduleTargetType(str, Enum):
    AGENT_MESSAGE = "agent_message"
    AUTOMATION_RUN = "automation_run"


class ScheduleStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DELETED = "deleted"


class ScheduleRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class ScheduleResponse(BaseModel):
    schedule_id: str
    owner_email: str
    name: str
    status: ScheduleStatus
    cron_expression: str
    timezone: str = "UTC"
    target_type: ScheduleTargetType
    target: dict[str, Any] = Field(default_factory=dict)
    source_type: str = "api"
    source_ref: dict[str, Any] = Field(default_factory=dict)
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class CreateScheduleRequest(BaseModel):
    name: str
    cron_expression: str
    timezone: str = "UTC"
    target_type: ScheduleTargetType
    target: dict[str, Any] = Field(default_factory=dict)
    source_type: str = "api"
    source_ref: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class UpdateScheduleRequest(BaseModel):
    name: Optional[str] = None
    cron_expression: Optional[str] = None
    timezone: Optional[str] = None
    target: Optional[dict[str, Any]] = None
    source_ref: Optional[dict[str, Any]] = None
    enabled: Optional[bool] = None


class ScheduleRunResponse(BaseModel):
    run_id: str
    schedule_id: str
    owner_email: str
    scheduled_for: datetime
    status: ScheduleRunStatus
    target_type: ScheduleTargetType
    target_ref: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None


class Schedule(BaseModel):
    schedule_id: str = Field(default_factory=lambda: str(uuid4()))
    owner_email: str
    name: str
    status: ScheduleStatus = ScheduleStatus.ACTIVE
    cron_expression: str
    timezone: str = "UTC"
    target_type: ScheduleTargetType
    target: dict[str, Any] = Field(default_factory=dict)
    source_type: str = "api"
    source_ref: dict[str, Any] = Field(default_factory=dict)
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"User#{self.owner_email}"

    @property
    def sk(self) -> str:
        return f"Schedule#{self.schedule_id}"

    def due_gsi_pk(self) -> str:
        return f"ScheduleDue#{self.status.value}"

    def due_gsi_sk(self) -> str:
        next_run = self.next_run_at or datetime.max.replace(tzinfo=timezone.utc)
        return f"{next_run.isoformat()}#Schedule#{self.schedule_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        item = {
            "pk": self.pk,
            "sk": self.sk,
            "entity_type": "Schedule",
            "schedule_id": self.schedule_id,
            "owner_email": self.owner_email,
            "name": self.name,
            "status": self.status.value,
            "cron_expression": self.cron_expression,
            "timezone": self.timezone,
            "target_type": self.target_type.value,
            "target": self.target,
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if self.next_run_at and self.status == ScheduleStatus.ACTIVE:
            item["gsi2_pk"] = self.due_gsi_pk()
            item["gsi2_sk"] = self.due_gsi_sk()
        return convert_floats_to_decimals(item)

    def to_lookup_items(self) -> list[dict[str, Any]]:
        refs: list[tuple[str, str]] = []
        agent_id = str(self.target.get("agent_id") or "").strip()
        conversation_id = str(self.target.get("conversation_id") or "").strip()
        automation_id = str(self.target.get("automation_id") or "").strip()
        if agent_id:
            refs.append((f"Agent#{agent_id}", "AgentScheduleLookup"))
        if conversation_id:
            refs.append((f"Conversation#{conversation_id}", "ConversationScheduleLookup"))
        if automation_id:
            refs.append((f"Automation#{automation_id}", "AutomationScheduleLookup"))

        return [
            convert_floats_to_decimals(
                {
                    "pk": pk,
                    "sk": self.sk,
                    "entity_type": entity_type,
                    "schedule_id": self.schedule_id,
                    "owner_email": self.owner_email,
                    "target_type": self.target_type.value,
                    "status": self.status.value,
                    "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
                    "created_at": self.created_at.isoformat(),
                }
            )
            for pk, entity_type in refs
        ]

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "Schedule":
        item = convert_decimals(item)
        return cls(
            schedule_id=item["schedule_id"],
            owner_email=item["owner_email"],
            name=item["name"],
            status=ScheduleStatus(item.get("status", ScheduleStatus.ACTIVE.value)),
            cron_expression=item["cron_expression"],
            timezone=item.get("timezone", "UTC"),
            target_type=ScheduleTargetType(item["target_type"]),
            target=item.get("target") or {},
            source_type=item.get("source_type", "api"),
            source_ref=item.get("source_ref") or {},
            next_run_at=datetime.fromisoformat(item["next_run_at"]) if item.get("next_run_at") else None,
            last_run_at=datetime.fromisoformat(item["last_run_at"]) if item.get("last_run_at") else None,
            created_by=item["created_by"],
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )

    def to_response(self) -> ScheduleResponse:
        return ScheduleResponse(**self.model_dump())


class ScheduleRun(BaseModel):
    run_id: str
    schedule_id: str
    owner_email: str
    scheduled_for: datetime
    status: ScheduleRunStatus = ScheduleRunStatus.PENDING
    target_type: ScheduleTargetType
    target_ref: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"Schedule#{self.schedule_id}"

    @property
    def sk(self) -> str:
        return f"Run#{self.scheduled_for.isoformat()}#{self.run_id}"

    @classmethod
    def deterministic_run_id(cls, schedule_id: str, scheduled_for: datetime) -> str:
        return f"{schedule_id}:{scheduled_for.isoformat()}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return convert_floats_to_decimals(
            {
                "pk": self.pk,
                "sk": self.sk,
                "entity_type": "ScheduleRun",
                "run_id": self.run_id,
                "schedule_id": self.schedule_id,
                "owner_email": self.owner_email,
                "scheduled_for": self.scheduled_for.isoformat(),
                "status": self.status.value,
                "target_type": self.target_type.value,
                "target_ref": self.target_ref,
                "output": self.output,
                "error": self.error,
                "started_at": self.started_at.isoformat(),
                "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            }
        )

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "ScheduleRun":
        item = convert_decimals(item)
        return cls(
            run_id=item["run_id"],
            schedule_id=item["schedule_id"],
            owner_email=item["owner_email"],
            scheduled_for=datetime.fromisoformat(item["scheduled_for"]),
            status=ScheduleRunStatus(item.get("status", ScheduleRunStatus.PENDING.value)),
            target_type=ScheduleTargetType(item["target_type"]),
            target_ref=item.get("target_ref") or {},
            output=item.get("output") or {},
            error=item.get("error"),
            started_at=datetime.fromisoformat(item["started_at"]),
            completed_at=datetime.fromisoformat(item["completed_at"]) if item.get("completed_at") else None,
        )

    def to_response(self) -> ScheduleRunResponse:
        return ScheduleRunResponse(**self.model_dump())
