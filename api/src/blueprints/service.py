"""Deploying a blueprint: validate it, plan it against the account, and apply it within the rate limit.

The dashboard's API and Ada both deploy through `deploy_blueprint`, so neither can skip a step. Each outcome is its
own type, and the caller turns it into its own kind of answer (an HTTP status, or a tool result for Ada).
"""

from dataclasses import dataclass
from typing import Any, Optional, Union

from fastapi import BackgroundTasks

from src.blueprints.executor import apply_blueprint, apply_rate_limit
from src.blueprints.issues import BlueprintInvalid, BlueprintIssue
from src.blueprints.models import Deployment, DeploymentStatus
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
    """Applied, or failed part-way: `deployment.status` says which."""

    validated: ValidatedBlueprint
    plan: Plan
    deployment: Deployment


DeployOutcome = Union[Invalid, Blocked, RateLimited, Deployed]


def deploy_blueprint(
    yaml: str,
    params: dict[str, Any],
    user_email: str,
    background_tasks: Optional[BackgroundTasks] = None,
) -> DeployOutcome:
    """Validated and planned again here, whatever the caller planned before: the account may have changed."""
    try:
        validated = validate_blueprint(yaml, params)
    except BlueprintInvalid as e:
        return Invalid(e.issues)
    plan = plan_blueprint(validated, user_email)
    if not plan.ok:
        return Blocked(plan)

    limiter = RateLimiter(apply_rate_limit())
    decision = limiter.acquire(user_email)
    if not decision.allowed:
        return RateLimited(decision.retry_after_seconds or 60)
    deployment = apply_blueprint(validated, plan, user_email, background_tasks)
    if deployment.status != DeploymentStatus.APPLIED:
        # Nothing (or only leftovers) was created, so the attempt shouldn't count against the limit.
        limiter.release(decision)
    return Deployed(validated, plan, deployment)
