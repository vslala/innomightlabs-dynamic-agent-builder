from typing import Any, Optional

from src.agents.models import Agent, CreateAgentRequest
from src.agents.repository import AgentRepository
from src.agents.service import AgentService, validate_provider_model
from src.blueprints.issues import BlueprintIssue
from src.blueprints.kinds.base import (
    Action,
    AppliedResource,
    ApplyContext,
    Change,
    Existing,
    NotFound,
    PlanContext,
    ResourceKind,
    Usage,
)
from src.blueprints.spec import AgentSpec, SkillEntry
from src.knowledge.repository import AgentKnowledgeBaseRepository
from src.settings.repository import get_provider_settings_repository
from src.skills.models import ActorKind, AgentSkill
from src.skills.repository import AgentSkillRepository
from src.skills.service import SkillService

#: The only architecture that uses knowledge bases and skills, so blueprints don't offer a choice.
BLUEPRINT_ARCHITECTURE = "krishna-memgpt"


def skill_audience(entry: SkillEntry) -> list[ActorKind] | None:
    return [ActorKind(value) for value in entry.available_to] or None


def skill_config(entry: SkillEntry) -> dict[str, Any]:
    return {key: value for key, value in (entry.config or {}).items() if value is not None}


def _audience(skill: AgentSkill) -> set[str]:
    return {ActorKind(kind).value for kind in skill.available_to}


def skill_changes(entry: SkillEntry, installed: AgentSkill) -> bool:
    """Whether the entry asks for something different from the install. Config it doesn't mention is kept."""
    config = skill_config(entry)
    wanted_audience = {ActorKind.OWNER.value, *entry.available_to}
    return (
        any(installed.config.get(key) != value for key, value in config.items())
        or wanted_audience != _audience(installed)
        or entry.enabled != installed.enabled
    )


class AgentKind(ResourceKind[AgentSpec]):
    kind = "Agent"
    label = "Agent"
    spec_model = AgentSpec
    exposes = ("id", "name")

    def find_existing(self, name: str, spec: AgentSpec, ctx: PlanContext) -> Optional[Existing]:
        repo = AgentRepository()
        if spec.id:
            agent = repo.find_agent_by_id(spec.id, ctx.user_email)
            if not agent:
                raise NotFound(f"There's no agent with id '{spec.id}' in your account.")
            matched_by = "id"
        else:
            agent = repo.find_by_name(spec.name, ctx.user_email)
            if not agent:
                return None
            matched_by = "name"
        return Existing(
            id=agent.agent_id,
            record=agent,
            matched_by=matched_by,  # type: ignore[arg-type]
            related={
                "kb_ids": {link.kb_id for link in AgentKnowledgeBaseRepository().find_kbs_for_agent(agent.agent_id)},
                "skills": {skill.skill_id: skill for skill in AgentSkillRepository().list_by_agent(agent.agent_id)},
            },
        )

    def differences(self, name: str, spec: AgentSpec, existing: Existing, ctx: PlanContext) -> list[str]:
        agent: Agent = existing.record
        changes = []
        if spec.name != agent.agent_name:
            changes.append(f"rename to '{spec.name}'")
        if spec.instructions.strip() != agent.agent_persona.strip():
            changes.append("update its instructions")
        if spec.provider != agent.agent_provider or (spec.model and spec.model != agent.agent_model):
            changes.append(f"switch to {spec.provider}" + (f" · {spec.model}" if spec.model else ""))
        if spec.description is not None and spec.description != agent.agent_description:
            changes.append("update its description")
        if spec.session_timeout_minutes is not None and spec.session_timeout_minutes != agent.session_timeout_minutes:
            changes.append(f"start conversations fresh after {spec.session_timeout_minutes} minutes")
        linked = existing.related["kb_ids"]
        for kb_name in spec.knowledge_bases:
            matched = ctx.matched.get(kb_name)
            if matched is None or matched.id not in linked:
                changes.append(f"link knowledge base '{kb_name}'")
        installed: dict[str, AgentSkill] = existing.related["skills"]
        for entry in spec.skills:
            skill = installed.get(entry.id)
            if skill is None:
                changes.append(f"add skill {entry.id.replace('_', ' ')}")
            elif skill_changes(entry, skill):
                changes.append(f"update skill {entry.id.replace('_', ' ')}")
        return changes

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

        installed = change.existing.related["skills"] if change.existing else {}
        service = SkillService()
        for index, entry in enumerate(spec.skills):
            if entry.id in installed:
                continue
            try:
                service.check_install(
                    skill_id=entry.id,
                    user_email=ctx.user_email,
                    raw_config=skill_config(entry),
                    enabled=entry.enabled,
                    available_to=skill_audience(entry),
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
        if spec.skills:
            parts.append(f"with skills {', '.join(entry.id for entry in spec.skills)}")
        return ", ".join(parts)

    def apply(self, name: str, spec: AgentSpec, ctx: ApplyContext) -> AppliedResource:
        agent = AgentService().create(
            CreateAgentRequest(
                agent_name=spec.name,
                agent_architecture=BLUEPRINT_ARCHITECTURE,
                agent_provider=spec.provider,
                agent_model=spec.model,
                agent_persona=spec.instructions,
                agent_description=spec.description,
                session_timeout_minutes=spec.session_timeout_minutes,
            ),
            ctx.user_email,
        )
        applied = self._applied(name, agent)
        try:
            self._link_and_install(applied, spec, ctx, linked=set(), installed={})
        except Exception:
            self.rollback(applied, ctx)
            raise
        return applied

    def update(self, name: str, spec: AgentSpec, change: Change, ctx: ApplyContext) -> AppliedResource:
        existing = change.existing
        assert existing is not None
        previous: Agent = existing.record
        updates: dict[str, Any] = {
            "agent_name": spec.name,
            "agent_persona": spec.instructions,
            "agent_provider": spec.provider,
        }
        if spec.model is not None:
            updates["agent_model"] = spec.model
        if spec.description is not None:
            updates["agent_description"] = spec.description
        if spec.session_timeout_minutes is not None:
            updates["session_timeout_minutes"] = spec.session_timeout_minutes
        agent = AgentRepository().save(previous.model_copy(update=updates))
        applied = self._applied(name, agent)
        applied.previous = {"agent": previous, "skills": {}}
        try:
            self._link_and_install(
                applied, spec, ctx, linked=existing.related["kb_ids"], installed=existing.related["skills"]
            )
        except Exception:
            self.restore(applied, ctx)
            raise
        return applied

    def _link_and_install(
        self,
        applied: AppliedResource,
        spec: AgentSpec,
        ctx: ApplyContext,
        *,
        linked: set[str],
        installed: dict[str, AgentSkill],
    ) -> None:
        """Adds what's missing and changes what differs. Never removes: links and skills the blueprint doesn't
        mention stay as they are."""
        links = AgentKnowledgeBaseRepository()
        for kb_name in spec.knowledge_bases:
            kb_id = ctx.applied[kb_name].id
            if kb_id not in linked:
                links.link(applied.id, kb_id, ctx.user_email)
                applied.cleanup["knowledge_bases"].append(kb_id)
        service = SkillService()
        for entry in spec.skills:
            existing_skill = installed.get(entry.id)
            if existing_skill is None:
                new = service.install_skill(
                    agent_id=applied.id,
                    skill_id=entry.id,
                    user_email=ctx.user_email,
                    raw_config=skill_config(entry),
                    enabled=entry.enabled,
                    available_to=skill_audience(entry),
                )
                applied.cleanup["skills"].append(new.installed_skill_id or new.skill_id)
            elif skill_changes(entry, existing_skill):
                installed_skill_id = existing_skill.installed_skill_id or existing_skill.skill_id
                # Merges with the stored config, so secrets set on the Skills tab are kept.
                service.update_installed(
                    agent_id=applied.id,
                    installed_skill_id=installed_skill_id,
                    enabled=entry.enabled,
                    raw_config=skill_config(entry) or None,
                    available_to=[ActorKind.OWNER, *(skill_audience(entry) or [])],
                )
                applied.previous["skills"][installed_skill_id] = existing_skill

    def kept(self, name: str, change: Change) -> AppliedResource:
        return self._applied(name, change.existing.record)  # type: ignore[union-attr]

    def _applied(self, name: str, agent: Agent) -> AppliedResource:
        return AppliedResource(
            name=name,
            kind=self.kind,
            id=agent.agent_id,
            attributes={"id": agent.agent_id, "name": agent.agent_name},
            cleanup={"knowledge_bases": [], "skills": []},
        )

    def _undo_additions(self, applied: AppliedResource, ctx: ApplyContext) -> None:
        service = SkillService()
        for installed_skill_id in applied.cleanup.get("skills", []):
            service.uninstall(agent_id=applied.id, installed_skill_id=installed_skill_id, user_email=ctx.user_email)
        links = AgentKnowledgeBaseRepository()
        for kb_id in applied.cleanup.get("knowledge_bases", []):
            links.unlink(applied.id, kb_id)

    def rollback(self, applied: AppliedResource, ctx: ApplyContext) -> None:
        self._undo_additions(applied, ctx)
        AgentRepository().delete_by_id(applied.id, ctx.user_email)

    def restore(self, applied: AppliedResource, ctx: ApplyContext) -> None:
        self._undo_additions(applied, ctx)
        service = SkillService()
        for installed_skill_id, before in (applied.previous or {}).get("skills", {}).items():
            service.update_installed(
                agent_id=applied.id,
                installed_skill_id=installed_skill_id,
                enabled=before.enabled,
                raw_config=dict(before.config) or None,
                available_to=list(before.available_to),
            )
        AgentRepository().save(applied.previous["agent"])
