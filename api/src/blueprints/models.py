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
    #: A rollback step failed too, or a removal failed after everything else was applied; `error` says which.
    FAILED_PARTIAL = "failed_partial"


class DeployedResource(BaseModel):
    kind: str
    id: str
    attributes: dict[str, str] = Field(default_factory=dict)


class DeploymentOutput(BaseModel):
    value: str
    description: Optional[str] = None


class JournalState(str, Enum):
    #: About to run, or running. If the apply stopped here, the command may or may not have happened.
    STARTED = "started"
    DONE = "done"
    UNDONE = "undone"
    UNDO_FAILED = "undo_failed"


class UndoRecord(BaseModel):
    action: str
    args: dict[str, Any] = Field(default_factory=dict)


class JournalEntry(BaseModel):
    """One command of an apply, recorded before it runs, with how to undo it."""

    command: str
    resource: str
    state: JournalState = JournalState.STARTED
    #: None for a command that can't be undone, or has nothing to undo.
    undo: Optional[UndoRecord] = None
    #: It brought `resource` into being, so undoing it means the deployment no longer has it.
    creates: bool = False
    #: It deletes `resource`.
    deletes: bool = False
    #: What it took away, in plain words.
    removal: Optional[str] = None


class DeploymentAction(str, Enum):
    APPLY = "apply"
    ROLLBACK = "rollback"
    REMOVE = "remove"


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
    #: What was taken away, in plain words, in the order it happened.
    removed: list[str] = Field(default_factory=list)
    #: Every command run so far, written before it runs, so an interrupted apply can still be put back.
    journal: list[JournalEntry] = Field(default_factory=list)
    #: Past the commit point: everything that can be undone has run, and only what can't is left.
    committed: bool = False
    #: The kit it's a version of, and which version; set once it changed something.
    kit_id: Optional[str] = None
    version: Optional[int] = None
    action: DeploymentAction = DeploymentAction.APPLY
    #: For a rollback, the version it went back to.
    rolled_back_to: Optional[int] = None
    #: The plan's steps, in plain words, so a kit's history says what each version did.
    steps: list[str] = Field(default_factory=list)
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
    #: Plan or apply as the next version of this kit. Without it, applying starts a new kit.
    kit_id: Optional[str] = None


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


# --- Kits -----------------------------------------------------------------------------------------------------


class KitSummary(BaseModel):
    kit_id: str
    title: str
    description: Optional[str] = None
    status: str
    current_version: int
    versions: int
    #: How many of each kind it holds, by kind.
    counts: dict[str, int] = Field(default_factory=dict)
    conversation_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class KitResourceView(BaseModel):
    name: str
    kind: str
    id: str
    title: str
    #: The dashboard page for it, with no host; empty when it has none.
    dashboard_path: str = ""


class KitVersionView(BaseModel):
    version: int
    deployment_id: str
    action: DeploymentAction
    status: DeploymentStatus
    #: What the kit declares now.
    current: bool = False
    rolled_back_to: Optional[int] = None
    steps: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    created_at: datetime


class KitDetail(KitSummary):
    resources: list[KitResourceView] = Field(default_factory=list)
    history: list[KitVersionView] = Field(default_factory=list)


class KitPlanResponse(BaseModel):
    ok: bool
    plan_id: Optional[str] = None
    steps: list[PlanStep] = Field(default_factory=list)
    blockers: list[BlueprintIssue] = Field(default_factory=list)
    removals: list[str] = Field(default_factory=list)


class RollbackRequest(BaseModel):
    version: int


class ApplyKitPlanRequest(BaseModel):
    plan_id: str
    #: For a rollback, the version it goes back to.
    version: Optional[int] = None
