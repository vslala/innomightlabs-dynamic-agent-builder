"""Automations in blueprints: a trigger and an ordered list of steps, so Ila can build what happens next, such as
emailing sales each time an agent captures a lead.

A blueprint writes an automation as the dashboard shows it, a chain: Start, the steps in order, Done. This kind
compiles that chain into the stored graph, and reads a stored graph back into it. An automation with branches or
several triggers can't be written that way, so a blueprint never changes one; it says so in the plan.
"""

import re
from dataclasses import dataclass, replace
from uuid import uuid4
from typing import Any, ClassVar, Mapping, Optional

from src.accounts.owner import Owner
from src.automations.errors import AutomationNotFoundError
from src.automations.models import (
    Automation,
    AutomationActionType,
    AutomationEdge,
    AutomationNode,
    AutomationNodeType,
    AutomationSkill,
    AutomationStatus,
    AutomationTrigger,
    AutomationTriggerType,
    CreateAutomationRequest,
    UpdateAutomationRequest,
    UpdateAutomationSkillRequest,
)
from src.automations.repository import AutomationRepository
from src.automations.service import AutomationService
from src.automations.triggers.models import LeadCapturedTriggerConfig, ScheduleTriggerConfig
from src.blueprints.commands import Command, Reversibility, Undo, Use, undo_action
from src.blueprints.issues import BlueprintIssue
from src.blueprints.kinds.agent import install_key, skill_config
from src.blueprints.kinds.base import (
    Action,
    AppliedResource,
    ApplyContext,
    Change,
    Existing,
    ManagedKind,
    NotFound,
    PlanContext,
    reconcile_context,
)
from src.blueprints.kinds.lead_form import missing_lead_forms
from src.blueprints.reconcile import Context, Outcome, reconcile
from src.blueprints.references import Reference
from src.blueprints.skills_schema import skill_variants
from src.blueprints.spec import (
    AutomationSpec,
    SkillEntry,
    StepSpec,
    TriggerSpec,
    lead_form_resource,
    lead_form_slug,
)
from src.automations.aliases import RESERVED_ALIASES

TEMPLATE = re.compile(r"\{\{\s*(.*?)\s*\}\}")
STEP_REFERENCE = re.compile(r"\bsteps\.([A-Za-z0-9_]+)")
#: Spacing for the dashboard's drawing of the chain
STEP_SPACING = 320


def _applied(name: str, automation: Automation) -> AppliedResource:
    return AppliedResource(
        name=name,
        kind="Automation",
        id=automation.automation_id,
        attributes={"id": automation.automation_id, "title": automation.title},
    )


def _service() -> AutomationService:
    return AutomationService()


# --- Reading a stored graph as a chain ------------------------------------------------------------------------


@dataclass(frozen=True)
class Chain:
    """A stored graph that is a trigger and a line of steps: what a blueprint can write."""

    steps: list[AutomationNode]
    trigger: AutomationTrigger


def read_chain(nodes: list[AutomationNode], edges: list[AutomationEdge], triggers: list[AutomationTrigger]) -> Optional[Chain]:
    """The graph as a chain, or None when it has branches, conditions or several triggers."""
    starts = [node for node in nodes if node.type == AutomationNodeType.START]
    finals = [node for node in nodes if node.type == AutomationNodeType.FINAL]
    if len(triggers) != 1 or len(starts) != 1 or len(finals) != 1 or len(edges) != len(nodes) - 1:
        return None
    by_id = {node.node_id: node for node in nodes}
    next_of: dict[str, str] = {}
    for edge in edges:
        if edge.source_node_id in next_of or edge.label != "next":
            return None
        next_of[edge.source_node_id] = edge.target_node_id

    steps: list[AutomationNode] = []
    current = starts[0].node_id
    while current in next_of:
        current = next_of[current]
        node = by_id.get(current)
        if node is None or len(steps) > len(nodes):
            return None
        if node.type == AutomationNodeType.FINAL:
            break
        if node.type != AutomationNodeType.ACTION or node.config.get("action_type") not in {
            AutomationActionType.INVOKE_AGENT.value,
            AutomationActionType.SKILL_ACTION.value,
        }:
            return None
        steps.append(node)
    covered = len(steps) + 2
    if current != finals[0].node_id or covered != len(nodes) or triggers[0].entry_node_id != starts[0].node_id:
        return None
    return Chain(steps=steps, trigger=triggers[0])


def _observed_trigger(trigger: AutomationTrigger, names: Mapping[str, str]) -> dict[str, Any]:
    config = trigger.config
    if trigger.type == AutomationTriggerType.SCHEDULE:
        return {"schedule": {
            "cron": config.get("cron_expression") or None,
            "run_at": config.get("run_at") or None,
            "timezone": config.get("timezone", "UTC"),
            "input": config.get("input") or {},
        }}
    if trigger.type == AutomationTriggerType.LEAD_CAPTURED:
        lead = LeadCapturedTriggerConfig.model_validate(config)
        return {"lead_captured": {
            "form": lead.form_slug,
            "agent": names.get(lead.agent_id, lead.agent_id) if lead.agent_id else None,
            "include_test_captures": lead.include_test_captures,
        }}
    return {"manual": {}}


def _observed_step(node: AutomationNode, names: Mapping[str, str]) -> dict[str, Any]:
    config = node.config
    name = node.alias or node.name
    if config["action_type"] == AutomationActionType.INVOKE_AGENT.value:
        agent_id = config["agent_id"]
        return {"name": name, "agent": names.get(agent_id, agent_id), "prompt": config["prompt_template"]}
    return {
        "name": name,
        "skill": config.get("skill_id") or str(config.get("installed_skill_id", "")).split(":")[0],
        "action": config["action"],
        "arguments": config.get("arguments") or {},
    }


def _observed_skill(skill: AutomationSkill) -> Optional[dict[str, Any]]:
    """An install as a blueprint's skill entry, or None for one a blueprint can't describe or never added."""
    variant = skill_variants().get(skill.skill_id)
    if variant is None or variant.required_secrets:
        return None
    entry: dict[str, Any] = {"id": skill.skill_id}
    config = {key: value for key, value in skill.config.items() if key in variant.config_fields}
    if config:
        entry["config"] = config
    if not skill.enabled:
        entry["enabled"] = False
    return entry


# --- Writing a chain as a stored graph ------------------------------------------------------------------------


def _agent_id(ref: str, ctx: ApplyContext) -> str:
    """An Agent of this blueprint becomes its id; anything else is already one."""
    return ctx.applied[ref].id if ref in ctx.applied else ref


def _step_node(automation_id: str, step: StepSpec, index: int, ctx: ApplyContext, node_id: str | None) -> AutomationNode:
    if step.agent is not None:
        config: dict[str, Any] = {
            "action_type": AutomationActionType.INVOKE_AGENT.value,
            "agent_id": _agent_id(step.agent, ctx),
            "prompt_template": step.prompt,
        }
    else:
        config = {
            "action_type": AutomationActionType.SKILL_ACTION.value,
            "skill_id": step.skill,
            "action": step.action,
            "arguments": step.arguments,
        }
    return AutomationNode(
        node_id=node_id or str(uuid4()),
        automation_id=automation_id,
        type=AutomationNodeType.ACTION,
        name=step.name.replace("_", " ").capitalize(),
        alias=step.name,
        position={"x": (index + 1) * STEP_SPACING, "y": 0},
        config=config,
    )


def _trigger_of(automation_id: str, spec: TriggerSpec, entry_node_id: str, ctx: ApplyContext, trigger_id: str | None):
    if spec.schedule is not None:
        kind, name = AutomationTriggerType.SCHEDULE, "Schedule"
        config: dict[str, Any] = ScheduleTriggerConfig(
            cron_expression=spec.schedule.cron or "",
            run_at=spec.schedule.run_at,  # type: ignore[arg-type]  # read as ISO 8601 by the model
            timezone=spec.schedule.timezone,
            input=spec.schedule.input,
        ).model_dump(mode="json", exclude_none=True)
        # Stored as written: the dashboard shows the text the person typed
        if spec.schedule.run_at:
            config["run_at"] = spec.schedule.run_at
    elif spec.lead_captured is not None:
        kind, name = AutomationTriggerType.LEAD_CAPTURED, "Lead captured"
        lead = spec.lead_captured
        config = {"include_test_captures": lead.include_test_captures}
        if lead.form:
            config["form_slug"] = lead_form_slug(lead.form)
        if lead.agent:
            config["agent_id"] = _agent_id(lead.agent, ctx)
    else:
        kind, name, config = AutomationTriggerType.MANUAL, "Manual", {}
    return AutomationTrigger(
        trigger_id=trigger_id or str(uuid4()),
        automation_id=automation_id,
        type=kind,
        name=name,
        enabled=True,
        entry_node_id=entry_node_id,
        config=config,
    )


def compile_chain(
    automation_id: str, spec: AutomationSpec, ctx: ApplyContext, current: Optional[Chain] = None
) -> tuple[list[AutomationNode], list[AutomationEdge], list[AutomationTrigger]]:
    """Start, the steps, Done, joined in order, and the trigger. Ids of what is already there are kept, so run
    history still points at the same steps."""
    kept = {node.alias: node.node_id for node in current.steps} if current else {}
    start = AutomationNode(automation_id=automation_id, type=AutomationNodeType.START, name="Start", position={"x": 0, "y": 0})
    steps = [_step_node(automation_id, step, index, ctx, kept.get(step.name)) for index, step in enumerate(spec.steps)]
    final = AutomationNode(
        automation_id=automation_id,
        type=AutomationNodeType.FINAL,
        name="Done",
        position={"x": (len(steps) + 1) * STEP_SPACING, "y": 0},
    )
    chain = [start, *steps, final]
    edges = [
        AutomationEdge(automation_id=automation_id, source_node_id=a.node_id, target_node_id=b.node_id, label="next")
        for a, b in zip(chain, chain[1:])
    ]
    same_kind = current and current.trigger.type.value == _trigger_type(spec.trigger)
    trigger = _trigger_of(
        automation_id, spec.trigger, start.node_id, ctx, current.trigger.trigger_id if same_kind and current else None
    )
    return chain, edges, [trigger]


def _trigger_type(trigger: TriggerSpec) -> str:
    return "schedule" if trigger.schedule else "lead_captured" if trigger.lead_captured else "manual"


# --- Commands -----------------------------------------------------------------------------------------------


@dataclass(kw_only=True)
class CreateAutomation(Command):
    spec: AutomationSpec
    #: Chosen when it's prepared, so the undo knows it even if the apply stops before the create returns.
    automation_id: str = ""

    reversibility: ClassVar[Reversibility] = Reversibility.COMPENSATABLE
    establishes: ClassVar[bool] = True
    creates: ClassVar[bool] = True

    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        self.automation_id = self.automation_id or str(uuid4())
        return Undo("delete_automation", {"automation_id": self.automation_id})

    def run(self, ctx: ApplyContext) -> None:
        graph = _service().create_automation(
            CreateAutomationRequest(title=self.spec.title, description=self.spec.description, status=AutomationStatus.DRAFT),
            ctx.owner,
            automation_id=self.automation_id,
        )
        ctx.applied[self.resource] = _applied(self.resource, graph.automation)


@undo_action("delete_automation")
def _delete_automation(args: dict[str, Any], owner: Owner) -> None:
    try:
        _service().delete_automation(args["automation_id"], owner)
    except AutomationNotFoundError:
        pass


@dataclass(kw_only=True)
class SaveAutomation(Command):
    """Its name and description."""

    automation_id: str
    fields: dict[str, Any]

    establishes: ClassVar[bool] = True

    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        current = _service().get_automation(self.automation_id, ctx.owner)
        before = {key: getattr(current, key) for key in self.fields}
        return Undo("restore_automation_fields", {"automation_id": self.automation_id, "fields": before})

    def run(self, ctx: ApplyContext) -> None:
        saved = _service().update_automation(self.automation_id, UpdateAutomationRequest(**self.fields), ctx.owner)
        ctx.applied[self.resource] = _applied(self.resource, saved)


@undo_action("restore_automation_fields")
def _restore_automation_fields(args: dict[str, Any], owner: Owner) -> None:
    _service().update_automation(args["automation_id"], UpdateAutomationRequest(**args["fields"]), owner)


@dataclass(kw_only=True)
class InstallAutomationSkill(Command):
    entry: SkillEntry

    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        config = skill_config(self.entry)
        return Undo("uninstall_automation_skill", {
            "automation_id": ctx.applied[self.resource].id, "installed_skill_id": install_key(self.entry, config),
        })

    def run(self, ctx: ApplyContext) -> None:
        _service().install_skill(
            automation_id=ctx.applied[self.resource].id,
            skill_id=self.entry.id,
            raw_config=skill_config(self.entry),
            owner=ctx.owner,
            enabled=self.entry.enabled,
        )


@undo_action("uninstall_automation_skill")
def _uninstall_automation_skill(args: dict[str, Any], owner: Owner) -> None:
    _service().delete_skill(args["automation_id"], args["installed_skill_id"], owner)


@dataclass(kw_only=True)
class UpdateAutomationSkill(Command):
    entry: SkillEntry
    installed_skill_id: str

    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        current = AutomationRepository().find_skill(ctx.applied[self.resource].id, self.installed_skill_id)
        if current is None:
            return None
        # Plain settings only: secrets are stored apart, and the update keeps them
        return Undo("restore_automation_skill", {
            "automation_id": current.automation_id,
            "installed_skill_id": self.installed_skill_id,
            "enabled": current.enabled,
            "config": dict(current.config),
        })

    def run(self, ctx: ApplyContext) -> None:
        _service().update_skill(
            ctx.applied[self.resource].id,
            self.installed_skill_id,
            UpdateAutomationSkillRequest(enabled=self.entry.enabled, config=skill_config(self.entry) or None),
            ctx.owner,
        )


@undo_action("restore_automation_skill")
def _restore_automation_skill(args: dict[str, Any], owner: Owner) -> None:
    _service().update_skill(
        args["automation_id"],
        args["installed_skill_id"],
        UpdateAutomationSkillRequest(enabled=args["enabled"], config=args["config"] or None),
        owner,
    )


@dataclass(kw_only=True)
class UninstallAutomationSkill(Command):
    """Its settings go with it, so it can't be undone."""

    automation_id: str
    installed_skill_id: str

    reversibility: ClassVar[Reversibility] = Reversibility.IRREVERSIBLE

    def run(self, ctx: ApplyContext) -> None:
        _service().delete_skill(self.automation_id, self.installed_skill_id, ctx.owner)


@dataclass(kw_only=True)
class SetAutomationChain(Command):
    """Its trigger and steps, written whole."""

    spec: AutomationSpec

    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        nodes, edges, triggers = AutomationRepository().get_graph(ctx.applied[self.resource].id)
        return Undo("restore_automation_graph", {
            "automation_id": ctx.applied[self.resource].id,
            "nodes": [node.model_dump(mode="json") for node in nodes],
            "edges": [edge.model_dump(mode="json") for edge in edges],
            "triggers": [trigger.model_dump(mode="json") for trigger in triggers],
        })

    def run(self, ctx: ApplyContext) -> None:
        automation_id = ctx.applied[self.resource].id
        nodes, edges, triggers = AutomationRepository().get_graph(automation_id)
        nodes, edges, triggers = compile_chain(automation_id, self.spec, ctx, read_chain(nodes, edges, triggers))
        _service().replace_graph(automation_id, nodes, edges, triggers, ctx.owner)


@undo_action("restore_automation_graph")
def _restore_automation_graph(args: dict[str, Any], owner: Owner) -> None:
    _service().replace_graph(
        args["automation_id"],
        [AutomationNode.model_validate(node) for node in args["nodes"]],
        [AutomationEdge.model_validate(edge) for edge in args["edges"]],
        [AutomationTrigger.model_validate(trigger) for trigger in args["triggers"]],
        owner,
    )


@dataclass(kw_only=True)
class SetAutomationStatus(Command):
    """Turn it on, so its trigger starts it, or off. Last: it's checked as a whole, strictly, when it goes on."""

    active: bool

    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        current = _service().get_automation(ctx.applied[self.resource].id, ctx.owner)
        return Undo("restore_automation_status", {"automation_id": current.automation_id, "status": current.status.value})

    def run(self, ctx: ApplyContext) -> None:
        status = AutomationStatus.ACTIVE if self.active else AutomationStatus.DISABLED
        _service().update_automation(ctx.applied[self.resource].id, UpdateAutomationRequest(status=status), ctx.owner)


@undo_action("restore_automation_status")
def _restore_automation_status(args: dict[str, Any], owner: Owner) -> None:
    _service().update_automation(
        args["automation_id"], UpdateAutomationRequest(status=AutomationStatus(args["status"])), owner
    )


@dataclass(kw_only=True)
class DeleteAutomation(Command):
    automation_id: str

    reversibility: ClassVar[Reversibility] = Reversibility.IRREVERSIBLE
    deletes: ClassVar[bool] = True

    def run(self, ctx: ApplyContext) -> None:
        _delete_automation({"automation_id": self.automation_id}, ctx.owner)


# --- The kind -----------------------------------------------------------------------------------------------


def _reconcile_context(ctx: PlanContext) -> Context:
    return replace(
        reconcile_context(ctx),
        keys={"skills": lambda item: _entry_key(item)},
        differs={"skills": lambda item, installed: _entry_differs(item, installed)},
    )


def _entry(item: Any) -> SkillEntry:
    return item if isinstance(item, SkillEntry) else SkillEntry.model_validate(item)


def _entry_key(item: Any) -> str:
    entry = _entry(item)
    return install_key(entry, skill_config(entry))


def _entry_differs(item: Any, installed: Any) -> bool:
    """Whether the entry asks for something different from the install. Config it doesn't mention is kept."""
    entry, there = _entry(item), _entry(installed)
    return any(there.config.get(key) != value for key, value in skill_config(entry).items()) or entry.enabled != there.enabled


class AutomationKind(ManagedKind[AutomationSpec]):
    kind = "Automation"
    label = "Automation"
    use_when = (
        "Do something automatically: on a schedule, or each time an agent captures a lead, such as email sales or "
        "post the lead to a CRM."
    )
    deletes = "its steps, schedule and run history"
    spec_model = AutomationSpec
    exposes = ("id", "title")
    feeds = "triggers"
    dashboard_path = "/dashboard/automations/{id}"
    export_name = "automation"

    def observe(self, record: Automation, names: Mapping[str, str]) -> dict[str, Any]:
        repository = AutomationRepository()
        chain = read_chain(*repository.get_graph(record.automation_id))
        resource: dict[str, Any] = {
            "kind": self.kind,
            "id": record.automation_id,
            "title": record.title,
            "enabled": record.status == AutomationStatus.ACTIVE,
        }
        if record.description:
            resource["description"] = record.description
        if chain is not None:
            resource["trigger"] = _observed_trigger(chain.trigger, names)
            resource["steps"] = [_observed_step(node, names) for node in chain.steps]
        skills = [entry for skill in repository.list_skills(record.automation_id) if (entry := _observed_skill(skill))]
        # Every automation can ask agents, so that skill is only written when it has settings to say
        resource["skills"] = [entry for entry in skills if entry["id"] != "agent_invocation" or "config" in entry]
        return resource

    def applied(self, name: str, record: Automation) -> AppliedResource:
        return _applied(name, record)

    def title(self, name: str, spec: AutomationSpec, resources: dict[str, Any]) -> str:
        return spec.title

    def card_details(self, spec: AutomationSpec) -> list[str]:
        start = (
            "On a schedule" if spec.trigger.schedule
            else "When a lead is captured" if spec.trigger.lead_captured
            else "Started by hand"
        )
        return [start, f"{len(spec.steps)} step{'s' if len(spec.steps) != 1 else ''}", "On" if spec.enabled else "Off, a draft"]

    def page_sections(self) -> list[str]:
        return [
            "### Reading what triggered it\n\n"
            "Steps read the event with smart values: `{{ trigger.lead.answers.email }}`, `{{ trigger.lead.capture_id }}` "
            "and `{{ trigger.lead.form_slug }}` for a captured lead, `{{ input.<key> }}` for a schedule's input, and "
            "`{{ steps.<name>.output }}` for an earlier step. Steps run in order; later ones may read earlier ones.",
        ]

    def references(self, name: str, spec: AutomationSpec) -> list[Reference]:
        references = [
            Reference(
                path=f"resources.{name}.steps[{index}].agent", target=step.agent, kind="Agent", where="this step",
                may_be_id=True, outward_wire="hands work to",
            )
            for index, step in enumerate(spec.steps)
            if step.agent
        ]
        lead = spec.trigger.lead_captured
        if lead and lead.form:
            references.append(Reference(
                path=f"resources.{name}.trigger.lead_captured.form", target=lead_form_resource(lead.form),
                kind="LeadForm", where="the trigger", may_be_id=True,
            ))
        if lead and lead.agent:
            references.append(Reference(
                path=f"resources.{name}.trigger.lead_captured.agent", target=lead.agent, kind="Agent",
                where="the trigger", may_be_id=True,
            ))
        return references

    def validate(self, name: str, spec: AutomationSpec) -> list[BlueprintIssue]:
        """What can be known from the spec alone: step names, what steps read, and the skills they use."""
        path = f"resources.{name}"
        issues: list[BlueprintIssue] = []
        earlier: set[str] = set()
        listed = {entry.id for entry in spec.skills} | {"agent_invocation"}
        for index, step in enumerate(spec.steps):
            step_path = f"{path}.steps[{index}]"
            if step.name in RESERVED_ALIASES or step.name in earlier:
                issues.append(BlueprintIssue(
                    path=f"{step_path}.name",
                    message=f"'{step.name}' can't be a step's name.",
                    hint="Step names are unique, and not one of: " + ", ".join(sorted(RESERVED_ALIASES)) + ".",
                ))
            issues += self._step_reads(step_path, step, earlier)
            if step.skill is not None:
                issues += self._skill_step(step_path, step, listed)
            earlier.add(step.name)
        issues += self._schedule(path, spec)
        for index, entry in enumerate(spec.skills):
            if entry.available_to:
                issues.append(BlueprintIssue(
                    path=f"{path}.skills[{index}].available_to",
                    message="An automation's skills aren't shared with visitors.",
                    hint="Remove `available_to`.",
                ))
        return issues

    @staticmethod
    def _step_reads(step_path: str, step: StepSpec, earlier: set[str]) -> list[BlueprintIssue]:
        """`{{ steps.<name> }}` must name a step before this one."""
        texts = [step.prompt or "", *[str(value) for value in step.arguments.values()]]
        read = {
            match.group(1) for text in texts for template in TEMPLATE.findall(text) for match in STEP_REFERENCE.finditer(template)
        }
        return [
            BlueprintIssue(
                path=step_path,
                message=f"This step reads '{name}', which isn't a step before it.",
                hint="A step can read only the steps above it: " + (", ".join(sorted(earlier)) or "there are none yet") + ".",
            )
            for name in sorted(read - earlier)
        ]

    @staticmethod
    def _skill_step(step_path: str, step: StepSpec, listed: set[str]) -> list[BlueprintIssue]:
        variant = skill_variants().get(step.skill or "")
        if variant is None:
            return [BlueprintIssue(path=f"{step_path}.skill", message=f"There's no skill called '{step.skill}'.")]
        if step.skill not in listed:
            return [BlueprintIssue(
                path=f"{step_path}.skill",
                message=f"{variant.skill.manifest.name} isn't one of this automation's skills.",
                hint=f"Add `- id: {step.skill}` under `skills`.",
            )]
        manifest_action = variant.skill.manifest.find_action(step.action or "")
        if manifest_action is None:
            offered = [action.name for action in variant.skill.manifest.actions]
            return [BlueprintIssue(
                path=f"{step_path}.action",
                message=f"{variant.skill.manifest.name} has no action '{step.action}'. It has: {', '.join(offered)}.",
            )]
        missing = [field for field in manifest_action.input_schema.get("required", []) if field not in step.arguments]
        return [BlueprintIssue(
            path=f"{step_path}.arguments",
            message=f"'{step.action}' needs {', '.join(missing)}.",
        )] if missing else []

    @staticmethod
    def _schedule(path: str, spec: AutomationSpec) -> list[BlueprintIssue]:
        schedule = spec.trigger.schedule
        if schedule is None:
            return []
        if bool(schedule.cron) == bool(schedule.run_at):
            return [BlueprintIssue(
                path=f"{path}.trigger.schedule",
                message="Set either `cron` to repeat or `run_at` to run once, not both.",
            )]
        return []

    def find_existing(self, name: str, spec: AutomationSpec, ctx: PlanContext) -> Optional[Existing]:
        service = _service()
        if spec.id:
            try:
                automation = service.get_automation(spec.id, ctx.owner)
            except AutomationNotFoundError:
                raise NotFound(f"There's no automation with id '{spec.id}' in your account.") from None
            return Existing(id=automation.automation_id, record=automation, matched_by="id")
        same = [
            automation for automation in service.list_automations(ctx.owner)
            if automation.owner_id == ctx.owner.user_id and automation.title == spec.title
        ]
        return Existing(id=same[0].automation_id, record=same[0], matched_by="name") if len(same) == 1 else None

    def reconcile(
        self, spec: AutomationSpec, existing: Optional[Existing], before: Optional[dict[str, Any]], ctx: PlanContext
    ) -> Outcome:
        return reconcile(spec, existing.observed if existing else None, before, _reconcile_context(ctx))

    def commands(
        self, name: str, spec: AutomationSpec, existing: Optional[Existing], outcome: Outcome, ctx: PlanContext
    ) -> list[Command]:
        uses = frozenset(ref.target for ref in self.references(name, spec))
        commands: list[Command] = [self._establish(name, spec, existing, outcome)]
        for item in outcome.items("added", "skills"):
            commands.append(InstallAutomationSkill(resource=name, entry=item.now, says=(item.says,)))
        for item in outcome.items("changed", "skills"):
            commands.append(UpdateAutomationSkill(resource=name, entry=item.now, installed_skill_id=item.key, says=(item.says,)))
        for item in outcome.items("removed", "skills"):
            commands.append(UninstallAutomationSkill(
                resource=name, automation_id=existing.id if existing else "", installed_skill_id=item.key, removal=item.says
            ))
        if existing is None or outcome.sets_field("trigger") or outcome.sets_field("steps"):
            says = tuple(change.says for change in outcome.sets if change.field in {"trigger", "steps"} and change.says)
            commands.append(SetAutomationChain(resource=name, uses=uses, spec=spec, says=says))
        # A new one starts as a draft, so there is nothing to turn off
        if (spec.enabled if existing is None else outcome.sets_field("enabled")):
            commands.append(SetAutomationStatus(resource=name, active=spec.enabled, says=("turn it on" if spec.enabled else "turn it off",)))
        return commands

    def _establish(self, name: str, spec: AutomationSpec, existing: Optional[Existing], outcome: Outcome) -> Command:
        if existing is None:
            return CreateAutomation(resource=name, spec=spec)
        fields = outcome.values(AutomationSpec)
        if not fields:
            return Use(resource=name, applied=_applied(name, existing.record))
        return SaveAutomation(resource=name, automation_id=existing.id, fields=fields, says=outcome.says())

    def check(self, name: str, spec: AutomationSpec, change: Change, ctx: PlanContext) -> list[BlueprintIssue]:
        path = f"resources.{name}"
        issues: list[BlueprintIssue] = []
        if change.existing is not None and "steps" not in change.existing.observed:
            issues.append(BlueprintIssue(
                path=path,
                message=f"'{spec.title}' has branches, conditions or several triggers, so a blueprint can't change it.",
                hint="Edit it in the dashboard, or choose another title for this one.",
            ))
        lead = spec.trigger.lead_captured
        if lead and lead.form:
            issues += missing_lead_forms([lead.form], f"{path}.trigger.lead_captured.form", ctx)
        service = _service()
        if change.action != Action.UNCHANGED:
            known = {_entry_key(item) for item in (change.existing.observed.get("skills", []) if change.existing else [])}
            for index, entry in enumerate(spec.skills):
                if _entry_key(entry) in known:
                    continue
                try:
                    service.validate_skill_config(skill_id=entry.id, raw_config=skill_config(entry), owner=ctx.owner)
                except ValueError as refused:
                    issues.append(BlueprintIssue(path=f"{path}.skills[{index}]", message=str(refused)))
        return issues

    def delete_commands(self, name: str, spec: AutomationSpec, existing: Existing, removal: str) -> list[Command]:
        uses = frozenset(ref.target for ref in self.references(name, spec))
        return [DeleteAutomation(resource=name, uses=uses, automation_id=existing.id, removal=removal)]

    def describe(self, name: str, spec: AutomationSpec) -> str:
        starts = (
            "on a schedule" if spec.trigger.schedule
            else "when a lead is captured" if spec.trigger.lead_captured
            else "by hand"
        )
        return f"Create the automation '{spec.title}', started {starts}, with {len(spec.steps)} step(s)" + (
            "" if spec.enabled else ", left as a draft"
        )
