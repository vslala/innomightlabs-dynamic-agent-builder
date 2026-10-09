"""Planning a validated blueprint against what already exists: what it creates, updates, removes or leaves
alone, the commands that do it in the order they must run, and what stops it. No side effects.

A kit's plan also has its last applied version (`before`). What that version declared and this one leaves out is
removed: a resource deleted, a link or skill taken away. What the kit never declared is never touched.
"""

from dataclasses import replace
from typing import Any, Mapping, Optional

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.blueprints.commands import Command, OrderError, Step, command_order
from src.blueprints.issues import BlueprintIssue
from src.blueprints.kinds import (
    Action,
    Change,
    Existing,
    LookupKind,
    ManagedKind,
    NotFound,
    PlanContext,
    kind_for,
    managed_kind_for,
)
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
    #: What was changed outside the blueprint since the kit's last version, and is left as it is.
    drift: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    steps: list[PlanStep]
    #: Anything here stops apply. Each names the part of the blueprint it's about.
    blockers: list[BlueprintIssue]
    #: What apply does with each resource, by name. Not part of any response.
    changes: dict[str, Change] = Field(default_factory=dict, exclude=True)
    #: What apply runs, in order, with the commit point. Not part of any response.
    commands: list[Step] = Field(default_factory=list, exclude=True)
    #: Resources this plan deletes, as the kit's last version wrote them, so the drawing can show them.
    removed_specs: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @property
    def ok(self) -> bool:
        return not self.blockers

    @property
    def changes_anything(self) -> bool:
        return any(step.action != Action.UNCHANGED for step in self.steps)

    @property
    def removals(self) -> list[str]:
        return [removal for step in self.steps for removal in step.removals]


def plan_blueprint(
    validated: ValidatedBlueprint, user_email: str, before: Optional[ValidatedBlueprint] = None
) -> Plan:
    """`before` is the kit's last applied version, with the kit's ids pinned; None for a new kit."""
    return _plan(validated.blueprint.resources, validated.order, before, user_email)


def plan_removal(before: ValidatedBlueprint, user_email: str) -> Plan:
    """Removing a kit: everything its last version declared, left out."""
    return _plan({}, [], before, user_email)


def _plan(
    resources: Mapping[str, Any], order: list[str], before: Optional[ValidatedBlueprint], user_email: str
) -> Plan:
    ctx = PlanContext(user_email=user_email)
    plan = Plan(steps=[], blockers=[])
    commands: list[Command] = []
    declared = before.blueprint.resources if before else {}
    kit_ids = {spec.id for spec in [*declared.values(), *resources.values()] if spec.id}
    ctx.pinned = {name: spec.id for name, spec in [*declared.items(), *resources.items()] if spec.id}

    # First what's left out, so what stays knows it's going (an agent isn't disconnected from a deleted base).
    left_out: list[tuple[str, PlanStep, list[Command]]] = []
    for name in before.order if before else []:
        spec = declared[name]
        if name in resources:
            if resources[name].kind != spec.kind:
                plan.blockers.append(BlueprintIssue(
                    path=f"resources.{name}.kind",
                    message=f"'{name}' was a {spec.kind} in the last version and is a {resources[name].kind} now.",
                    hint="Give the new one a different name; the old one is removed when it's left out.",
                ))
            continue
        kind = kind_for(spec.kind)
        if isinstance(kind, LookupKind):
            # It belongs to the account, so it stays; but agents that leave it out stop using it, so they need to
            # see that they use it now.
            found = kind.find_existing(name, spec, ctx) if spec.id else None
            if found is not None:
                ctx.matched[name] = found
            continue
        left_out.append((name, *_removal(name, spec, managed_kind_for(spec.kind), ctx, plan)))

    agents = kb_pages = 0
    for name in order:
        spec = resources[name]
        kind = kind_for(spec.kind)
        try:
            existing = kind.find_existing(name, spec, ctx)
        except NotFound as e:
            plan.blockers.append(BlueprintIssue(path=f"resources.{name}.id", message=str(e),
                                                hint="Leave `id` out to create a new one."))
            existing = None
        if existing is None:
            ctx.created.add(name)
        else:
            # What it links to is named as the blueprint names it; links to anything else aren't the blueprint's.
            names = {matched.id: matched_name for matched_name, matched in ctx.matched.items()}
            existing = replace(existing, observed=kind.observe(existing.record, names))
            ctx.matched[name] = existing
        last = declared.get(name)
        outcome = kind.reconcile(spec, existing, last.model_dump() if last is not None else None, ctx)
        resource_commands = kind.commands(name, spec, existing, outcome, ctx)
        commands += resource_commands
        if existing is None:
            change = Change(action=Action.CREATE)
            summary = kind.describe(name, spec)
        else:
            differences = tuple(said for command in resource_commands for said in command.says)
            removals = tuple(command.removal for command in resource_commands if command.removal)
            change = Change(
                action=Action.UPDATE if differences or removals else Action.UNCHANGED,
                existing=existing,
                changes=differences,
                removals=removals,
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
            drift=[f"{drift.field.replace('_', ' ')} was changed outside the blueprint; it stays as it is"
                   for drift in outcome.drift],
        ))
        plan.blockers += kind.check(name, spec, change, ctx)
        usage = kind.usage(spec, change)
        agents += usage.agents
        kb_pages += usage.kb_pages

    # A resource left out under its old name but found again under a new one (by its id, or its name) is renamed,
    # and carries on: it's not deleted.
    carried_on = {matched.id for name, matched in ctx.matched.items() if name in resources}
    first: list[PlanStep] = []
    for name, step, deleting in left_out:
        existing = plan.changes[name].existing
        if existing is not None and existing.id in carried_on:
            del plan.changes[name]
            plan.removed_specs.pop(name, None)
            continue
        blockers = managed_kind_for(declared[name].kind).delete_blockers(name, existing, kit_ids) if existing else []
        if blockers:
            plan.blockers += blockers
            plan.changes[name] = Change(action=Action.UNCHANGED, existing=existing)
            plan.removed_specs.pop(name, None)
            step = step.model_copy(update={"action": Action.UNCHANGED, "removals": [],
                                           "summary": f"{step.summary.split(':')[0]}: not possible, it's used outside this kit"})
            deleting = []
        first.append(step)
        commands += deleting
    plan.steps = [*first, *plan.steps]
    plan.blockers += _renames(plan, resources, declared)
    try:
        plan.commands = command_order(commands)
    except OrderError as e:
        plan.blockers.append(BlueprintIssue(path="resources", message=f"These steps can't be put in order: {e}."))

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


def _removal(
    name: str, spec: Any, kind: ManagedKind[Any], ctx: PlanContext, plan: Plan
) -> tuple[PlanStep, list[Command]]:
    """A resource the kit's last version declared and this one leaves out. Already gone counts as done, so
    applying the same blueprint again is a no-op."""
    try:
        existing = kind.find_existing(name, spec, ctx) if spec.id else None
    except NotFound:
        existing = None
    if existing is None:
        plan.changes[name] = Change(action=Action.UNCHANGED)
        step = PlanStep(resource=name, kind=spec.kind, action=Action.UNCHANGED,
                        summary=f"{kind.label} '{getattr(spec, 'name', None) or name}' is already gone")
        return step, []
    ctx.matched[name] = existing
    ctx.removing.add(name)
    removal = f"delete {kind.label.lower()} '{_title(name, spec, existing)}': {kind.deletes}"
    plan.changes[name] = Change(action=Action.REMOVE, existing=existing, removals=(removal,))
    plan.removed_specs[name] = spec
    step = PlanStep(resource=name, kind=spec.kind, action=Action.REMOVE, summary=removal[0].upper() + removal[1:],
                    removals=[removal], existing_id=existing.id)
    return step, kind.delete_commands(name, spec, existing, removal)


def _renames(plan: Plan, resources: Mapping[str, Any], declared: Mapping[str, Any]) -> list[BlueprintIssue]:
    """A resource deleted and a new one of the same kind and name built in its place is almost always a rename that
    lost its id. Doing it would lose what the old one held (an agent's conversations, a base's content), so ask."""
    issues = []
    for old in plan.removed_specs:
        before = declared[old]
        for new, spec in resources.items():
            if plan.changes.get(new) and plan.changes[new].action == Action.CREATE and spec.kind == before.kind and (
                getattr(spec, "name", None) and getattr(spec, "name", None) == getattr(before, "name", None)
            ):
                issues.append(BlueprintIssue(
                    path=f"resources.{new}",
                    message=f"'{new}' looks like '{old}' renamed. As written, the old {kind_for(spec.kind).label.lower()} "
                    "is deleted and a new one built in its place.",
                    hint=f"To keep it, give '{new}' the id `{before.id}`. To replace it, give the new one a different name.",
                ))
    return issues


def _limit_issue(check) -> list[BlueprintIssue]:
    try:
        check()
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
        return [BlueprintIssue(path="resources", message=detail.get("message", "Your plan's limit is reached."),
                               hint="Upgrade your plan, or create fewer agents or pages.")]
    return []
