"""Deploying a blueprint: validate it, plan it against its kit, and apply it within the rate limit, recording the
result as the kit's next version.

The dashboard's API, Ada, and a kit's rollback and removal all deploy through here, so none of them can skip a step.
Each outcome is its own type, and the caller turns it into its own kind of answer (an HTTP status, or a tool result
for Ada).
"""

from dataclasses import dataclass
from typing import Any, Optional, Union

from fastapi import BackgroundTasks

from src.blueprints.executor import apply_blueprint, apply_rate_limit
from src.blueprints.issues import BlueprintInvalid, BlueprintIssue
from src.blueprints.kits import Kit, KitError, KitPlan, active_kit, declared, pin, record_version
from src.blueprints.models import Deployment, DeploymentAction, DeploymentStatus
from src.blueprints.planner import Plan, plan_blueprint
from src.blueprints.validator import ValidatedBlueprint, validate_blueprint
from src.rate_limits.limiter import RateLimiter


@dataclass(frozen=True)
class Invalid:
    issues: list[BlueprintIssue]


@dataclass(frozen=True)
class Blocked:
    """The account changed since it was planned: a name was taken, or a limit was reached."""

    plan: Plan


@dataclass(frozen=True)
class RateLimited:
    retry_after_seconds: int


@dataclass(frozen=True)
class Deployed:
    """Applied, or failed part-way: `deployment.status` says which. `kit` is the kit it's a version of."""

    validated: ValidatedBlueprint
    plan: Plan
    deployment: Deployment
    kit: Optional[Kit]


DeployOutcome = Union[Invalid, Blocked, RateLimited, Deployed]


def apply_planned(
    planned: KitPlan,
    owner_email: str,
    kit: Optional[Kit],
    background_tasks: Optional[BackgroundTasks] = None,
    conversation_id: Optional[str] = None,
) -> DeployOutcome:
    """Applies a plan within the rate limit and records it as the kit's next version (a new kit for a first build)."""
    if not planned.plan.ok:
        return Blocked(planned.plan)
    limiter = RateLimiter(apply_rate_limit())
    decision = limiter.acquire(owner_email)
    if not decision.allowed:
        return RateLimited(decision.retry_after_seconds or 60)
    deployment = apply_blueprint(
        planned.validated, planned.plan, owner_email, background_tasks,
        deployment_fields={
            "kit_id": kit.kit_id if kit else None,
            "action": planned.action,
            "rolled_back_to": planned.version,
        },
    )
    if deployment.status != DeploymentStatus.APPLIED:
        # Nothing (or only leftovers) was created, so the attempt shouldn't count against the limit.
        limiter.release(decision)
    return Deployed(planned.validated, planned.plan, deployment, record_version(kit, deployment, planned, conversation_id))


def deploy_blueprint(
    yaml: str,
    params: dict[str, Any],
    owner_email: str,
    background_tasks: Optional[BackgroundTasks] = None,
    *,
    kit_id: Optional[str] = None,
    baseline: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> DeployOutcome:
    """Validates, plans against the kit and applies: a new kit without `kit_id`, its next version with it. The
    dashboard's API and Ada both deploy through here, so neither can skip a step."""
    try:
        kit = active_kit(owner_email, kit_id) if kit_id else None
        text = pin(yaml, kit)
        validated = validate_blueprint(text, params)
        before = declared(kit, baseline)
    except BlueprintInvalid as e:
        return Invalid(e.issues)
    except KitError as e:
        return Invalid([BlueprintIssue(path="", message=str(e))])
    planned = KitPlan(validated, plan_blueprint(validated, owner_email, before), "", DeploymentAction.APPLY)
    return apply_planned(planned, owner_email, kit, background_tasks, conversation_id)


def apply_kit_plan(
    planned: KitPlan, owner_email: str, kit_id: str, plan_id: str, background_tasks: Optional[BackgroundTasks] = None
) -> DeployOutcome:
    """Applies a kit's rollback or removal, only if it's the plan the person saw: planned again just now, it must
    have the same `plan_id`, so nothing has changed in between."""
    if plan_id != planned.plan_id:
        return Invalid([BlueprintIssue(path="", message="The kit changed since you saw this plan. Look at it again.")])
    try:
        kit = active_kit(owner_email, kit_id)
    except KitError as e:
        return Invalid([BlueprintIssue(path="", message=str(e))])
    return apply_planned(planned, owner_email, kit, background_tasks)
