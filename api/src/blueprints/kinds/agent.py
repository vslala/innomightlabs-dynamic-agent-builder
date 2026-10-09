from dataclasses import dataclass
from typing import Any, ClassVar, Mapping, Optional
from uuid import uuid4

from src.agents.models import Agent, CreateAgentRequest
from src.agents.repository import AgentRepository
from src.agents.service import AgentService, validate_provider_model
from src.blueprints.commands import Command, Reversibility, Undo, Use, undo_action
from src.blueprints.issues import BlueprintIssue
from src.blueprints.kinds.base import (
    Action,
    AppliedResource,
    ApplyContext,
    Change,
    Existing,
    ManagedKind,
    NotFound,
    PlanContext,
    Usage,
)
from src.blueprints.reconcile import Context, Outcome, reconcile
from src.blueprints.references import Reference, skill_references
from src.blueprints.skills_schema import skill_variants
from src.blueprints.spec import AgentSpec, SkillEntry
from src.connectors.mcp.repository import get_mcp_connection_repository
from src.connectors.mcp.service import get_mcp_connector_service
from src.knowledge.models import KnowledgeBaseStatus
from src.knowledge.repository import AgentKnowledgeBaseRepository, KnowledgeBaseRepository
from src.settings.repository import get_provider_settings_repository
from src.skills.models import ActorKind, AgentSkill
from src.skills.identity import installed_skill_id_for
from src.skills.registry import get_skill_registry
from src.skills.repository import AgentSkillRepository
from src.skills.service import SkillService

#: The only architecture that uses knowledge bases and skills, so blueprints don't offer a choice.
BLUEPRINT_ARCHITECTURE = "krishna-memgpt"


def skill_audience(entry: SkillEntry) -> list[ActorKind] | None:
    return [ActorKind(value) for value in entry.available_to] or None


def skill_config(entry: SkillEntry, agent_ids: dict[str, str] | None = None) -> dict[str, Any]:
    """The entry's settings, with any Agent named by its blueprint name swapped for that agent's id."""
    config = {key: value for key, value in (entry.config or {}).items() if value is not None}
    variant = skill_variants().get(entry.id)
    for field_name in variant.agent_fields if variant else []:
        value = config.get(field_name)
        if isinstance(value, str) and agent_ids and value in agent_ids:
            config[field_name] = agent_ids[value]
    return config


def install_key(entry: SkillEntry, config: dict[str, Any]) -> str:
    """The install this entry is: the skill id, or for a skill that can be installed more than once, the id its
    identifying settings give (two `send_email` entries to different recipients are two installs)."""
    loaded = get_skill_registry().get(entry.id)
    if loaded is None:
        return entry.id
    try:
        normalized = get_skill_registry().validate_config(entry.id, config)
    except ValueError:
        normalized = config
    return installed_skill_id_for(loaded.manifest, normalized)


def pending_agents(entry: SkillEntry, config: dict[str, Any], new_agents: set[str]) -> set[str]:
    """Settings that still name an Agent this blueprint is about to create, so there's no id to check yet."""
    variant = skill_variants().get(entry.id)
    return {name for name in (variant.agent_fields if variant else []) if config.get(name) in new_agents}


def _count(n: int, text: str) -> str:
    return text.format(n=n) + ("s" if n > 1 else "")


def _skill_entry(installed: AgentSkill) -> Optional[dict[str, Any]]:
    """An install as a blueprint's skill entry, or None for one a blueprint can't describe."""
    variant = skill_variants().get(installed.skill_id)
    if variant is None or variant.required_secrets:
        return None
    entry: dict[str, Any] = {"id": installed.skill_id}
    config = {key: value for key, value in installed.config.items() if key in variant.config_fields}
    if config:
        entry["config"] = config
    audience = [ActorKind(kind).value for kind in installed.available_to if ActorKind(kind) != ActorKind.OWNER]
    if audience and variant.shareable:
        entry["available_to"] = audience
    if not installed.enabled:
        entry["enabled"] = False
    return entry


def _entry(item: Any) -> SkillEntry:
    """A skill entry, from the blueprint or as `observe` wrote an install."""
    return item if isinstance(item, SkillEntry) else SkillEntry.model_validate(item)


def _skill_key(item: Any, ids: dict[str, str]) -> str:
    entry = _entry(item)
    return install_key(entry, skill_config(entry, ids))


def _skill_differs(item: Any, installed: Any, ids: dict[str, str]) -> bool:
    """Whether the entry asks for something different from the install. Config it doesn't mention is kept."""
    entry, there = _entry(item), _entry(installed)
    return (
        any(there.config.get(key) != value for key, value in skill_config(entry, ids).items())
        or set(entry.available_to) != set(there.available_to)
        or entry.enabled != there.enabled
    )


def _skill_uses(name: str, entry: SkillEntry) -> frozenset[str]:
    """The agents a skill setting names, which must exist before it's installed."""
    return frozenset(ref.target for ref in skill_references(name, [entry]))


def _reconcile_context(ctx: PlanContext) -> Context:
    ids = ctx.ids()
    return Context(
        titles={name: str(getattr(matched.record, "name", name)) for name, matched in ctx.matched.items()},
        removing=frozenset(ctx.removing),
        keys={"skills": lambda item: _skill_key(item, ids)},
        differs={"skills": lambda item, installed: _skill_differs(item, installed, ids)},
        # `remove_skills` names skills, so it takes away every install of one.
        named_by={"skills": lambda listed, installed: _entry(installed).id == listed},
    )


def _applied(name: str, agent: Agent) -> AppliedResource:
    return AppliedResource(
        name=name, kind="Agent", id=agent.agent_id, attributes={"id": agent.agent_id, "name": agent.agent_name}
    )


def _label(skill_id: str) -> str:
    return skill_id.replace("_", " ")


# --- Commands -----------------------------------------------------------------------------------------------


@dataclass(kw_only=True)
class CreateAgent(Command):
    request: CreateAgentRequest
    #: Chosen when it's prepared, so the undo knows it even if the apply stops before the create returns.
    agent_id: str = ""

    reversibility: ClassVar[Reversibility] = Reversibility.COMPENSATABLE
    establishes: ClassVar[bool] = True
    creates: ClassVar[bool] = True

    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        self.agent_id = self.agent_id or str(uuid4())
        return Undo("delete_new_agent", {"agent_id": self.agent_id})

    def run(self, ctx: ApplyContext) -> None:
        agent = AgentService().create(self.request, ctx.user_email, agent_id=self.agent_id)
        ctx.applied[self.resource] = _applied(self.resource, agent)


@undo_action("delete_new_agent")
def _delete_new_agent(args: dict[str, Any], user_email: str) -> None:
    # The same delete as the dashboard's, so the dream schedule `create` added goes too, not left firing nightly.
    if AgentRepository().find_agent_by_id(args["agent_id"], user_email):
        AgentService().delete(args["agent_id"], user_email)


@dataclass(kw_only=True)
class SaveAgent(Command):
    agent_id: str
    fields: dict[str, Any]

    establishes: ClassVar[bool] = True

    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        current = AgentRepository().find_agent_by_id(self.agent_id, ctx.user_email)
        before = {key: getattr(current, key) for key in self.fields} if current else {}
        return Undo("restore_agent", {"agent_id": self.agent_id, "fields": before})

    def run(self, ctx: ApplyContext) -> None:
        ctx.applied[self.resource] = _applied(self.resource, _save_agent(self.agent_id, self.fields, ctx.user_email))


def _save_agent(agent_id: str, fields: dict[str, Any], user_email: str) -> Agent:
    current = AgentRepository().find_agent_by_id(agent_id, user_email)
    if current is None:
        raise RuntimeError("The agent was deleted since the plan. Plan again.")
    return AgentRepository().save(current.model_copy(update=fields))


@undo_action("restore_agent")
def _restore_agent(args: dict[str, Any], user_email: str) -> None:
    if args["fields"]:
        _save_agent(args["agent_id"], args["fields"], user_email)


@dataclass(kw_only=True)
class LinkKnowledgeBase(Command):
    knowledge_base: str

    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        return Undo("unlink_knowledge_base", self._ids(ctx))

    def run(self, ctx: ApplyContext) -> None:
        ids = self._ids(ctx)
        AgentKnowledgeBaseRepository().link(ids["agent_id"], ids["kb_id"], ctx.user_email)

    def _ids(self, ctx: ApplyContext) -> dict[str, str]:
        return {"agent_id": ctx.applied[self.resource].id, "kb_id": ctx.applied[self.knowledge_base].id}


@dataclass(kw_only=True)
class UnlinkKnowledgeBase(LinkKnowledgeBase):
    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        return Undo("link_knowledge_base", self._ids(ctx))

    def run(self, ctx: ApplyContext) -> None:
        ids = self._ids(ctx)
        AgentKnowledgeBaseRepository().unlink(ids["agent_id"], ids["kb_id"])


@undo_action("unlink_knowledge_base")
def _unlink_knowledge_base(args: dict[str, Any], user_email: str) -> None:
    AgentKnowledgeBaseRepository().unlink(args["agent_id"], args["kb_id"])


@undo_action("link_knowledge_base")
def _link_knowledge_base(args: dict[str, Any], user_email: str) -> None:
    AgentKnowledgeBaseRepository().link(args["agent_id"], args["kb_id"], user_email)


@dataclass(kw_only=True)
class EnableTools(Command):
    connection: str

    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        return Undo("disable_tools", self._ids(ctx))

    def run(self, ctx: ApplyContext) -> None:
        _enable_tools(self._ids(ctx), ctx.user_email)

    def _ids(self, ctx: ApplyContext) -> dict[str, str]:
        return {"agent_id": ctx.applied[self.resource].id, "mcp_id": ctx.applied[self.connection].id}


@dataclass(kw_only=True)
class DisableTools(EnableTools):
    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        return Undo("enable_tools", self._ids(ctx))

    def run(self, ctx: ApplyContext) -> None:
        _disable_tools(self._ids(ctx), ctx.user_email)


@undo_action("enable_tools")
def _enable_tools(args: dict[str, Any], user_email: str) -> None:
    get_mcp_connector_service().enable_for_agent(owner_email=user_email, agent_id=args["agent_id"], mcp_id=args["mcp_id"])


@undo_action("disable_tools")
def _disable_tools(args: dict[str, Any], user_email: str) -> None:
    get_mcp_connector_service().disable_for_agent(owner_email=user_email, agent_id=args["agent_id"], mcp_id=args["mcp_id"])


@dataclass(kw_only=True)
class InstallSkill(Command):
    entry: SkillEntry

    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        config = skill_config(self.entry, _ids(ctx))
        return Undo("uninstall_skill", {
            "agent_id": ctx.applied[self.resource].id, "installed_skill_id": install_key(self.entry, config),
        })

    def run(self, ctx: ApplyContext) -> None:
        SkillService().install_skill(
            agent_id=ctx.applied[self.resource].id,
            skill_id=self.entry.id,
            user_email=ctx.user_email,
            raw_config=skill_config(self.entry, _ids(ctx)),
            enabled=self.entry.enabled,
            available_to=skill_audience(self.entry),
        )


@undo_action("uninstall_skill")
def _uninstall_skill(args: dict[str, Any], user_email: str) -> None:
    SkillService().uninstall(agent_id=args["agent_id"], installed_skill_id=args["installed_skill_id"], user_email=user_email)


@dataclass(kw_only=True)
class UpdateSkill(Command):
    entry: SkillEntry
    installed_skill_id: str

    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        agent_id = ctx.applied[self.resource].id
        current = AgentSkillRepository().find_by_id(agent_id, self.installed_skill_id)
        if current is None:
            return None
        return Undo("restore_skill", {
            "agent_id": agent_id,
            "installed_skill_id": self.installed_skill_id,
            # Plain settings only: secrets are stored apart, and the update keeps them.
            "enabled": current.enabled,
            "config": dict(current.config),
            "available_to": [ActorKind(kind).value for kind in current.available_to],
        })

    def run(self, ctx: ApplyContext) -> None:
        config = skill_config(self.entry, _ids(ctx))
        # Merges with the stored config, so secrets set on the Skills tab are kept.
        SkillService().update_installed(
            agent_id=ctx.applied[self.resource].id,
            installed_skill_id=self.installed_skill_id,
            enabled=self.entry.enabled,
            raw_config=config or None,
            available_to=[ActorKind.OWNER, *(skill_audience(self.entry) or [])],
        )


@undo_action("restore_skill")
def _restore_skill(args: dict[str, Any], user_email: str) -> None:
    SkillService().update_installed(
        agent_id=args["agent_id"],
        installed_skill_id=args["installed_skill_id"],
        enabled=args["enabled"],
        raw_config=args["config"] or None,
        available_to=[ActorKind(kind) for kind in args["available_to"]],
    )


@dataclass(kw_only=True)
class UninstallSkill(Command):
    """Its settings and secrets go with it, so it can't be undone."""

    agent_id: str
    installed_skill_id: str

    reversibility: ClassVar[Reversibility] = Reversibility.IRREVERSIBLE

    def run(self, ctx: ApplyContext) -> None:
        SkillService().uninstall(
            agent_id=self.agent_id, installed_skill_id=self.installed_skill_id, user_email=ctx.user_email
        )


@dataclass(kw_only=True)
class DeleteAgent(Command):
    agent_id: str

    reversibility: ClassVar[Reversibility] = Reversibility.IRREVERSIBLE
    deletes: ClassVar[bool] = True

    def run(self, ctx: ApplyContext) -> None:
        AgentService().delete(self.agent_id, ctx.user_email)


def _ids(ctx: ApplyContext) -> dict[str, str]:
    return {name: resource.id for name, resource in ctx.applied.items()}


# --- The kind -----------------------------------------------------------------------------------------------


class AgentKind(ManagedKind[AgentSpec]):
    kind = "Agent"
    label = "Agent"
    use_when = "Anything people chat with: a support assistant, a docs helper, an agent with skills such as forms or email."
    deletes = "its conversations, skills, widget keys and API keys go with it"
    spec_model = AgentSpec
    exposes = ("id", "name")
    feeds = "chats through"
    dashboard_path = "/dashboard/agents/{id}"
    export_name = "agent"

    def linked(self, agent_id: str, user_email: str) -> list[tuple[str, str, Any]]:
        """(kind, id, record) of every resource the agent links to, in link order."""
        found: list[tuple[str, str, Any]] = []
        kbs = KnowledgeBaseRepository()
        for link in AgentKnowledgeBaseRepository().find_kbs_for_agent(agent_id):
            kb = kbs.find_by_id(link.kb_id, user_email)
            if kb is not None and kb.status != KnowledgeBaseStatus.DELETED:
                found.append(("KnowledgeBase", kb.kb_id, kb))
        connections = get_mcp_connection_repository()
        for mcp_link in connections.list_agent_connections(agent_id):
            connection = connections.find_connection(user_email, mcp_link.mcp_id) if mcp_link.enabled else None
            if connection is not None:
                found.append(("McpConnection", connection.mcp_id, connection))
        return found

    def observe(self, record: Agent, names: Mapping[str, str]) -> dict[str, Any]:
        """Skills a blueprint can't describe (ones that need a secret to install) are left out; applying never
        removes a skill, so they stay on the agent as they are."""
        resource: dict[str, Any] = {
            "kind": self.kind,
            "id": record.agent_id,
            "name": record.agent_name,
            "provider": record.agent_provider,
            "instructions": record.agent_persona,
            "session_timeout_minutes": record.session_timeout_minutes,
        }
        if record.agent_model:
            resource["model"] = record.agent_model
        if record.agent_description:
            resource["description"] = record.agent_description
        linked = self.linked(record.agent_id, record.created_by)
        for field_name, kind in (("knowledge_bases", "KnowledgeBase"), ("mcp_connections", "McpConnection")):
            targets = [names[linked_id] for linked_kind, linked_id, _ in linked if linked_kind == kind and linked_id in names]
            if targets:
                resource[field_name] = targets
        skills = [entry for skill in AgentSkillRepository().list_by_agent(record.agent_id) if (entry := _skill_entry(skill))]
        if skills:
            resource["skills"] = skills
        return resource

    def card_details(self, spec: AgentSpec) -> list[str]:
        details = [f"Thinks with {spec.provider}" + (f" · {spec.model}" if spec.model else "")]
        if spec.skills:
            variants = skill_variants()
            names = [variants[entry.id].skill.manifest.name if entry.id in variants else entry.id for entry in spec.skills]
            details.append("Skills: " + ", ".join(names))
        if spec.knowledge_bases:
            details.append(_count(len(spec.knowledge_bases), "Answers from {n} knowledge base"))
        if spec.mcp_connections:
            details.append(_count(len(spec.mcp_connections), "Uses tools from {n} connection"))
        return details

    def references(self, name: str, spec: AgentSpec) -> list[Reference]:
        """Its links, and any skill setting that names another agent."""
        return [*super().references(name, spec), *skill_references(name, spec.skills)]

    def find_existing(self, name: str, spec: AgentSpec, ctx: PlanContext) -> Optional[Existing]:
        repo = AgentRepository()
        if spec.id:
            agent = repo.find_agent_by_id(spec.id, ctx.user_email)
            if not agent:
                raise NotFound(f"There's no agent with id '{spec.id}' in your account.")
            return Existing(id=agent.agent_id, record=agent, matched_by="id")
        agent = repo.find_by_name(spec.name, ctx.user_email)
        return Existing(id=agent.agent_id, record=agent, matched_by="name") if agent else None

    def applied(self, name: str, record: Agent) -> AppliedResource:
        return _applied(name, record)

    def commands(self, name: str, spec: AgentSpec, existing: Optional[Existing], ctx: PlanContext) -> list[Command]:
        """Adds what's missing and changes what differs. Takes away only what `remove_*` names: links and skills
        the blueprint doesn't mention stay as they are."""
        outcome = reconcile(spec, existing.observed if existing else None, ctx=_reconcile_context(ctx))
        commands: list[Command] = [self._establish(name, spec, existing, outcome)]
        for item in outcome.items("added", "knowledge_bases"):
            commands.append(LinkKnowledgeBase(
                resource=name, uses=frozenset({item.now}), knowledge_base=item.now, says=(item.says,)
            ))
        for item in outcome.items("removed", "knowledge_bases"):
            commands.append(UnlinkKnowledgeBase(
                resource=name, uses=frozenset({item.actual}), knowledge_base=item.actual, removal=item.says
            ))
        for item in outcome.items("added", "mcp_connections"):
            commands.append(EnableTools(resource=name, uses=frozenset({item.now}), connection=item.now, says=(item.says,)))
        for item in outcome.items("removed", "mcp_connections"):
            commands.append(DisableTools(
                resource=name, uses=frozenset({item.actual}), connection=item.actual, removal=item.says
            ))
        for item in outcome.items("added", "skills"):
            commands.append(InstallSkill(resource=name, uses=_skill_uses(name, item.now), entry=item.now, says=(item.says,)))
        for item in outcome.items("changed", "skills"):
            commands.append(UpdateSkill(
                resource=name, uses=_skill_uses(name, item.now), entry=item.now, installed_skill_id=item.key,
                says=(item.says,),
            ))
        for item in outcome.items("removed", "skills"):
            commands.append(UninstallSkill(
                resource=name, agent_id=existing.id if existing else "", installed_skill_id=item.key, removal=item.says
            ))
        return commands

    def _establish(self, name: str, spec: AgentSpec, existing: Optional[Existing], outcome: Outcome) -> Command:
        if existing is None:
            return CreateAgent(resource=name, request=CreateAgentRequest(
                agent_name=spec.name,
                agent_architecture=BLUEPRINT_ARCHITECTURE,
                agent_provider=spec.provider,
                agent_model=spec.model,
                agent_persona=spec.instructions,
                agent_description=spec.description,
                session_timeout_minutes=spec.session_timeout_minutes,
            ))
        fields = outcome.values(AgentSpec)
        if not fields:
            return Use(resource=name, applied=_applied(name, existing.record))
        return SaveAgent(resource=name, agent_id=existing.id, fields=fields, says=outcome.says())

    def delete_commands(self, name: str, spec: AgentSpec, existing: Existing, removal: str) -> list[Command]:
        uses = frozenset(ref.target for ref in self.references(name, spec) if not ref.removes)
        return [DeleteAgent(resource=name, uses=uses, agent_id=existing.id, removal=removal)]

    def check(self, name: str, spec: AgentSpec, change: Change, ctx: PlanContext) -> list[BlueprintIssue]:
        path = f"resources.{name}"
        issues: list[BlueprintIssue] = []
        if change.action == Action.UNCHANGED:
            return issues
        same_name = AgentRepository().find_by_name(spec.name, ctx.user_email)
        if same_name and (change.existing is None or same_name.agent_id != change.existing.id):
            issues.append(BlueprintIssue(
                path=f"{path}.name",
                message=f"You already have another agent called '{spec.name}'.",
                hint="Choose a different name.",
            ))

        provider_ready = get_provider_settings_repository().find_by_provider(ctx.user_email, spec.provider)
        try:
            validate_provider_model(ctx.user_email, spec.provider, None)
        except ValueError:
            provider_ready = None
        if not provider_ready:
            issues.append(BlueprintIssue(
                path=f"{path}.provider",
                message=f"The provider '{spec.provider}' isn't set up on your account.",
                hint="Set it up in Settings > Provider Configuration, or choose a provider you've already set up.",
            ))
        elif spec.model:
            try:
                validate_provider_model(ctx.user_email, spec.provider, spec.model)
            except ValueError:
                issues.append(BlueprintIssue(
                    path=f"{path}.model",
                    message=f"'{spec.model}' isn't a model {spec.provider} offers you.",
                    hint="Leave `model` out to use the provider's default.",
                ))

        ids = ctx.ids()
        installed = {_skill_key(entry, ids) for entry in (change.existing.observed.get("skills", []) if change.existing else [])}
        service = SkillService()
        for index, entry in enumerate(spec.skills):
            config = skill_config(entry, ids)
            if install_key(entry, config) in installed:
                continue
            try:
                service.check_install(
                    skill_id=entry.id,
                    user_email=ctx.user_email,
                    raw_config=config,
                    enabled=entry.enabled,
                    available_to=skill_audience(entry),
                    pending_fields=pending_agents(entry, config, ctx.created),
                )
            except ValueError as e:
                issues.append(BlueprintIssue(path=f"{path}.skills[{index}]", message=str(e)))
        return issues

    def usage(self, spec: AgentSpec, change: Change) -> Usage:
        return Usage(agents=1 if change.action == Action.CREATE else 0)

    def describe(self, name: str, spec: AgentSpec) -> str:
        parts = [f"Create agent '{spec.name}' on {spec.provider}"]
        if spec.knowledge_bases:
            parts.append(f"linked to {', '.join(spec.knowledge_bases)}")
        if spec.mcp_connections:
            parts.append(f"using the tools of {', '.join(spec.mcp_connections)}")
        if spec.skills:
            parts.append(f"with skills {', '.join(entry.id for entry in spec.skills)}")
        return ", ".join(parts)
