from typing import Any

from src.agents.models import CreateAgentRequest
from src.agents.repository import AgentRepository
from src.agents.service import AgentService, validate_provider_model
from src.blueprints.issues import BlueprintIssue
from src.blueprints.kinds.base import AppliedResource, ApplyContext, PlanContext, ResourceKind, Usage
from src.blueprints.spec import AgentSpec, SkillEntry
from src.knowledge.repository import AgentKnowledgeBaseRepository
from src.settings.repository import get_provider_settings_repository
from src.skills.models import ActorKind
from src.skills.service import SkillService

#: The only architecture that uses knowledge bases and skills, so blueprints don't offer a choice.
BLUEPRINT_ARCHITECTURE = "krishna-memgpt"


def skill_audience(entry: SkillEntry) -> list[ActorKind] | None:
    return [ActorKind(value) for value in entry.available_to] or None


def skill_config(entry: SkillEntry) -> dict[str, Any]:
    return {key: value for key, value in (entry.config or {}).items() if value is not None}


class AgentKind(ResourceKind[AgentSpec]):
    kind = "Agent"
    spec_model = AgentSpec
    exposes = ("id", "name")

    def check(self, name: str, spec: AgentSpec, ctx: PlanContext) -> list[BlueprintIssue]:
        path = f"resources.{name}"
        issues: list[BlueprintIssue] = []
        if AgentRepository().find_by_name(spec.name, ctx.user_email):
            issues.append(BlueprintIssue(
                path=f"{path}.name",
                message=f"You already have an agent called '{spec.name}'.",
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

        service = SkillService()
        for index, entry in enumerate(spec.skills):
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

    def usage(self, spec: AgentSpec) -> Usage:
        return Usage(agents=1)

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
        applied = AppliedResource(
            name=name,
            kind=self.kind,
            id=agent.agent_id,
            attributes={"id": agent.agent_id, "name": agent.agent_name},
            cleanup={"knowledge_bases": [], "skills": []},
        )
        try:
            links = AgentKnowledgeBaseRepository()
            for kb_name in spec.knowledge_bases:
                kb_id = ctx.applied[kb_name].id
                links.link(agent.agent_id, kb_id, ctx.user_email)
                applied.cleanup["knowledge_bases"].append(kb_id)
            service = SkillService()
            for entry in spec.skills:
                installed = service.install_skill(
                    agent_id=agent.agent_id,
                    skill_id=entry.id,
                    user_email=ctx.user_email,
                    raw_config=skill_config(entry),
                    enabled=entry.enabled,
                    available_to=skill_audience(entry),
                )
                applied.cleanup["skills"].append(installed.installed_skill_id or installed.skill_id)
        except Exception:
            self.rollback(applied, ctx)
            raise
        return applied

    def rollback(self, applied: AppliedResource, ctx: ApplyContext) -> None:
        service = SkillService()
        for installed_skill_id in applied.cleanup.get("skills", []):
            service.uninstall(agent_id=applied.id, installed_skill_id=installed_skill_id, user_email=ctx.user_email)
        links = AgentKnowledgeBaseRepository()
        for kb_id in applied.cleanup.get("knowledge_bases", []):
            links.unlink(applied.id, kb_id)
        AgentRepository().delete_by_id(applied.id, ctx.user_email)
