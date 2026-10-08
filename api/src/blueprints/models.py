"""The deployment record of a blueprint apply, and the HTTP request and response shapes."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from src.blueprints.issues import BlueprintIssue
from src.blueprints.planner import PlanStep


class DeploymentStatus(str, Enum):
    APPLYING = "applying"
    APPLIED = "applied"
    #: Rolled back cleanly; nothing was left behind.
    FAILED = "failed"
    #: A rollback step failed too; `resources` lists what's left to clean up.
    FAILED_PARTIAL = "failed_partial"


class DeployedResource(BaseModel):
    kind: str
    id: str
    attributes: dict[str, str] = Field(default_factory=dict)


class DeploymentOutput(BaseModel):
    value: str
    description: Optional[str] = None


class Deployment(BaseModel):
    """
    What one blueprint apply created.

    DynamoDB: pk=User#{user_email}, sk=BlueprintDeployment#{created_at}#{deployment_id}
    """

    deployment_id: str = Field(default_factory=lambda: str(uuid4()))
    user_email: str
    blueprint_name: str
    blueprint_title: str
    blueprint_yaml: str
    params: dict[str, Any] = Field(default_factory=dict)
    status: DeploymentStatus = DeploymentStatus.APPLYING
    resources: dict[str, DeployedResource] = Field(default_factory=dict)
    outputs: dict[str, DeploymentOutput] = Field(default_factory=dict)
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"User#{self.user_email}"

    @property
    def sk(self) -> str:
        return f"BlueprintDeployment#{self.created_at.isoformat()}#{self.deployment_id}"


class DeploymentSummary(BaseModel):
    deployment_id: str
    blueprint_name: str
    blueprint_title: str
    status: DeploymentStatus
    created_at: datetime


class BlueprintRequest(BaseModel):
    yaml: str
    params: Optional[dict[str, Any]] = None


class ValidateResponse(BaseModel):
    valid: bool
    issues: list[BlueprintIssue] = Field(default_factory=list)
    #: The params as a SchemaForm, when the blueprint is valid.
    params_form: Optional[dict[str, Any]] = None


class PlanResponse(BaseModel):
    ok: bool
    steps: list[PlanStep] = Field(default_factory=list)
    blockers: list[BlueprintIssue] = Field(default_factory=list)
    #: Validation problems; when present there's no plan.
    issues: list[BlueprintIssue] = Field(default_factory=list)
