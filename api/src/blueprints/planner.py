"""Planning a validated blueprint against what already exists: what it creates, updates, removes or leaves
alone, and what stops it. No side effects."""

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.blueprints.issues import BlueprintIssue
from src.blueprints.kinds import Action, Change, Existing, NotFound, PlanContext, ResourceKind, kind_for
from src.blueprints.validator import ValidatedBlueprint
from src.rate_limits.service import RateLimitService


class PlanStep(BaseModel):
    resource: str
    kind: str
    action: Action = Action.CREATE
    summary: str
    #: For an update, each change in plain words.
    changes: list[str] = Field(default_factory=list)
    #: What it takes away, in plain words. These can't be undone, so they're listed apart.
    removals: list[str] = Field(default_factory=list)
    #: The existing resource it updates or keeps.
    existing_id: str | None = None


class Plan(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    steps: list[PlanStep]
    #: Anything here stops apply. Each names the part of the blueprint it's about.
    blockers: list[BlueprintIssue]
    #: What apply does with each resource, by name. Not part of any response.
    changes: dict[str, Change] = Field(default_factory=dict, exclude=True)

    @property
    def ok(self) -> bool:
        return not self.blockers

    @property
    def changes_anything(self) -> bool:
        return any(step.action != Action.UNCHANGED for step in self.steps)

    @property
    def removals(self) -> list[str]:
        return [removal for step in self.steps for removal in step.removals]


def plan_blueprint(validated: ValidatedBlueprint, user_email: str) -> Plan:
    ctx = PlanContext(user_email=user_email)
    plan = Plan(steps=[], blockers=[])
    agents = kb_pages = 0
    for name in validated.order:
        spec = validated.blueprint.resources[name]
        kind = kind_for(spec.kind)
        if spec.remove:
            plan.steps.append(_removal_step(name, spec, kind, ctx, plan))
            continue
        try:
            existing = kind.find_existing(name, spec, ctx)
        except NotFound as e:
            plan.blockers.append(BlueprintIssue(path=f"resources.{name}.id", message=str(e),
                                                hint="Leave `id` out to create a new one."))
            existing = None
        if existing is None:
            ctx.created.add(name)
            change = Change(action=Action.CREATE)
            summary = kind.describe(name, spec)
        else:
            ctx.matched[name] = existing
            differences = kind.differences(name, spec, existing, ctx)
            removals = kind.removals(name, spec, existing, ctx)
            change = Change(
                action=Action.UPDATE if differences or removals else Action.UNCHANGED,
                existing=existing,
                changes=tuple(differences),
                removals=tuple(removals),
            )
            title = _title(name, spec, existing)
            summary = (
                f"Update {kind.label.lower()} '{title}': " + "; ".join([*differences, *removals])
                if differences or removals
                else f"Keep {kind.label.lower()} '{title}' as it is"
            )
        plan.changes[name] = change
        plan.steps.append(PlanStep(
            resource=name,
            kind=spec.kind,
            action=change.action,
            summary=summary,
            changes=list(change.changes),
            removals=list(change.removals),
            existing_id=existing.id if existing else None,
        ))
        plan.blockers += kind.check(name, spec, change, ctx)
        usage = kind.usage(spec, change)
        agents += usage.agents
        kb_pages += usage.kb_pages

    # Called directly: the subscription middleware only sees the HTTP routes, not blueprint applies.
    limits = RateLimitService()
    if agents:
        plan.blockers += _limit_issue(lambda: limits.check_agent_limit(user_email, additional=agents))
    if kb_pages:
        plan.blockers += _limit_issue(lambda: limits.check_kb_pages_limit(user_email, kb_pages))
    return plan


def _title(name: str, spec: Any, existing: Existing) -> str:
    # A widget key's spec often has no name; the one it matched does.
    return getattr(spec, "name", None) or getattr(existing.record, "name", None) or name


def _removal_step(name: str, spec: Any, kind: ResourceKind[Any], ctx: PlanContext, plan: Plan) -> PlanStep:
    """A resource marked `remove`. Already gone counts as done, so applying the same blueprint again is a no-op."""
    try:
        existing = kind.find_existing(name, spec, ctx)
    except NotFound:
        existing = None
    if existing is None:
        plan.changes[name] = Change(action=Action.UNCHANGED)
        return PlanStep(resource=name, kind=spec.kind, action=Action.UNCHANGED,
                        summary=f"{kind.label} '{spec.name or name}' is already gone")
    ctx.matched[name] = existing
    removal = f"delete {kind.label.lower()} '{_title(name, spec, existing)}': {kind.deletes}"
    plan.changes[name] = Change(action=Action.REMOVE, existing=existing, removals=(removal,))
    return PlanStep(resource=name, kind=spec.kind, action=Action.REMOVE, summary=removal[0].upper() + removal[1:],
                    removals=[removal], existing_id=existing.id)


def _limit_issue(check) -> list[BlueprintIssue]:
    try:
        check()
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
        return [BlueprintIssue(path="resources", message=detail.get("message", "Your plan's limit is reached."),
                               hint="Upgrade your plan, or create fewer agents or pages.")]
    return []
