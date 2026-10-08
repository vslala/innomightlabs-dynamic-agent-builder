"""Planning a validated blueprint: what it will create, and what stops it. No side effects."""

from fastapi import HTTPException
from pydantic import BaseModel

from src.blueprints.issues import BlueprintIssue
from src.blueprints.kinds import PlanContext, kind_for
from src.blueprints.validator import ValidatedBlueprint
from src.rate_limits.service import RateLimitService


class PlanStep(BaseModel):
    resource: str
    kind: str
    action: str = "create"
    summary: str


class Plan(BaseModel):
    steps: list[PlanStep]
    #: Anything here stops apply. Each names the part of the blueprint it's about.
    blockers: list[BlueprintIssue]

    @property
    def ok(self) -> bool:
        return not self.blockers


def plan_blueprint(validated: ValidatedBlueprint, user_email: str) -> Plan:
    ctx = PlanContext(user_email=user_email)
    steps: list[PlanStep] = []
    blockers: list[BlueprintIssue] = []
    agents = kb_pages = 0
    for name in validated.order:
        spec = validated.blueprint.resources[name]
        kind = kind_for(spec.kind)
        steps.append(PlanStep(resource=name, kind=spec.kind, summary=kind.describe(name, spec)))
        blockers += kind.check(name, spec, ctx)
        usage = kind.usage(spec)
        agents += usage.agents
        kb_pages += usage.kb_pages

    # Called directly: the subscription middleware only sees the HTTP routes, not blueprint applies.
    limits = RateLimitService()
    if agents:
        blockers += _limit_issue(lambda: limits.check_agent_limit(user_email, additional=agents))
    if kb_pages:
        blockers += _limit_issue(lambda: limits.check_kb_pages_limit(user_email, kb_pages))
    return Plan(steps=steps, blockers=blockers)


def _limit_issue(check) -> list[BlueprintIssue]:
    try:
        check()
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
        return [BlueprintIssue(path="resources", message=detail.get("message", "Your plan's limit is reached."),
                               hint="Upgrade your plan, or create fewer agents or pages.")]
    return []
