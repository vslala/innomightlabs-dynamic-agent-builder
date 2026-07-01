from __future__ import annotations

from typing import Any

import src.form_models as form_models
from src.agent_marketplace.models import (
    ArchiveMarketplaceAgentResponse,
    ImportMarketplaceAgentRequest,
    ImportMarketplaceAgentResponse,
    ImportedMarketplaceSkillResponse,
    MarketplaceAgentDetailResponse,
    MarketplaceAgentSkillTemplate,
    MarketplaceAgentStatus,
    MarketplaceAgentSummaryResponse,
    MarketplaceAgentTemplate,
    MarketplaceImportPlanAgent,
    MarketplaceImportPlanResponse,
    MarketplaceSkillImportForm,
    PublishMarketplaceAgentRequest,
    PublishMarketplaceAgentResponse,
)
from src.agent_marketplace.repository import AgentMarketplaceRepository, get_agent_marketplace_repository
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.agents.schemas import get_create_agent_form
from src.form_options import FormOptionsContext, validate_form_options
from src.skills.models import AgentSkill
from src.skills.repository import AgentSkillRepository, get_agent_skill_repository
from src.skills.service import SkillService, get_skill_service


class AgentMarketplaceService:
    def __init__(
        self,
        repository: AgentMarketplaceRepository | None = None,
        agent_repository: AgentRepository | None = None,
        skill_repository: AgentSkillRepository | None = None,
        skill_service: SkillService | None = None,
    ):
        self.repository = repository or get_agent_marketplace_repository()
        self.agent_repository = agent_repository or AgentRepository()
        self.skill_repository = skill_repository or get_agent_skill_repository()
        self.skill_service = skill_service or get_skill_service()

    def list_agents(self, *, query: str | None = None, limit: int = 20) -> list[MarketplaceAgentSummaryResponse]:
        return [
            template.to_summary_response()
            for template in self.repository.list_latest_published(query=query, limit=limit)
        ]

    def get_agent(self, template_id: str) -> MarketplaceAgentDetailResponse:
        template = self._published_template(template_id)
        return template.to_detail_response()

    def get_import_plan(self, *, template_id: str, user_email: str) -> MarketplaceImportPlanResponse:
        template = self._published_template(template_id)
        skill_forms = [
            self._skill_import_form(skill, user_email)
            for skill in template.skills
        ]
        return MarketplaceImportPlanResponse(
            template_id=template.template_id,
            agent=MarketplaceImportPlanAgent(
                default_name=template.agent_name,
                default_provider=template.agent_provider,
                default_model=template.agent_model,
                allow_model_override=template.allow_model_override,
                description=template.agent_description,
                persona_preview=template.agent_persona,
            ),
            skill_forms=skill_forms,
        )

    def import_agent(
        self,
        *,
        template_id: str,
        user_email: str,
        request: ImportMarketplaceAgentRequest,
    ) -> ImportMarketplaceAgentResponse:
        template = self._published_template(template_id)
        self._validate_skill_configs(template, request.skill_configs, user_email)

        provider = request.agent_provider if template.allow_model_override and request.agent_provider else template.agent_provider
        model = request.agent_model if template.allow_model_override and request.agent_model else template.agent_model
        self._validate_provider_model(user_email, provider, model)

        agent = Agent(
            agent_name=(request.agent_name or template.agent_name).strip(),
            agent_architecture=template.agent_architecture,
            agent_provider=provider,
            agent_model=model,
            agent_persona=template.agent_persona,
            agent_description=template.agent_description,
            created_by=user_email,
        )
        saved_agent = self.agent_repository.save(agent)
        installed: list[AgentSkill] = []
        try:
            for skill in template.skills:
                config = self._merged_skill_config(skill, request.skill_configs)
                installed.append(
                    self.skill_service.install_skill(
                        agent_id=saved_agent.agent_id,
                        skill_id=skill.skill_id,
                        user_email=user_email,
                        raw_config=config,
                        enabled=skill.enabled_on_import,
                    )
                )
        except Exception:
            for installed_skill in installed:
                self.skill_service.uninstall(
                    agent_id=saved_agent.agent_id,
                    installed_skill_id=installed_skill.installed_skill_id,
                    user_email=user_email,
                )
            self.agent_repository.delete_by_id(saved_agent.agent_id, user_email)
            raise

        self.repository.increment_import_count(template.template_id)
        return ImportMarketplaceAgentResponse(
            agent_id=saved_agent.agent_id,
            agent_name=saved_agent.agent_name,
            installed_skills=[
                ImportedMarketplaceSkillResponse(
                    template_skill_key=skill.template_skill_key,
                    installed_skill_id=installed_skill.installed_skill_id,
                    skill_id=installed_skill.skill_id,
                )
                for skill, installed_skill in zip(template.skills, installed, strict=False)
            ],
        )

    def publish_agent(
        self,
        *,
        user_email: str,
        request: PublishMarketplaceAgentRequest,
    ) -> PublishMarketplaceAgentResponse:
        agent = self.agent_repository.find_agent_by_id(request.agent_id, user_email)
        if not agent:
            raise ValueError("Agent not found")

        latest = self.repository.find_latest_for_source_agent(
            source_agent_id=agent.agent_id,
            publisher_user_email=user_email,
        )
        version = (latest.template_version + 1) if latest else 1
        parent_template_id = latest.parent_template_id if latest else None

        template = MarketplaceAgentTemplate(
            title=request.title,
            template_version=version,
            parent_template_id=parent_template_id,
            changelog=request.changelog,
            short_description=request.short_description,
            full_description=request.full_description,
            agent_name=agent.agent_name,
            agent_architecture=agent.agent_architecture,
            agent_provider=agent.agent_provider,
            agent_model=agent.agent_model,
            agent_persona=agent.agent_persona,
            agent_description=agent.agent_description,
            skills=self._published_skill_templates(agent.agent_id, request.included_skill_ids),
            source_agent_id=agent.agent_id,
            publisher_user_email=user_email,
            publisher_display_name=user_email.split("@", 1)[0],
            tags=request.tags,
            status=request.status,
        )
        template.parent_template_id = template.parent_template_id or template.template_id
        template.latest_template_id = template.template_id
        saved = self.repository.save(template)
        if latest and latest.latest_template_id != saved.template_id:
            latest.latest_template_id = saved.template_id
            self.repository.save(latest)
        return PublishMarketplaceAgentResponse(
            template_id=saved.template_id,
            status=saved.status,
            title=saved.title,
            template_version=saved.template_version,
        )

    def archive_agent(self, *, template_id: str, user_email: str) -> ArchiveMarketplaceAgentResponse:
        template = self.repository.find_by_id(template_id)
        if not template or template.publisher_user_email != user_email:
            raise ValueError("Marketplace agent not found")
        template.status = MarketplaceAgentStatus.ARCHIVED
        saved = self.repository.save(template)
        return ArchiveMarketplaceAgentResponse(template_id=saved.template_id, status=saved.status)

    def _published_template(self, template_id: str) -> MarketplaceAgentTemplate:
        template = self.repository.find_by_id(template_id)
        if not template or template.status != MarketplaceAgentStatus.PUBLISHED:
            raise ValueError("Marketplace agent not found")
        if template.latest_template_id and template.latest_template_id != template.template_id:
            latest = self.repository.find_by_id(template.latest_template_id)
            if latest and latest.status == MarketplaceAgentStatus.PUBLISHED:
                return latest
        return template

    def _skill_import_form(self, skill: MarketplaceAgentSkillTemplate, user_email: str) -> MarketplaceSkillImportForm:
        loaded = self.skill_service.registry.get(skill.skill_id)
        if not loaded:
            raise ValueError(f"Unknown skill: {skill.skill_id}")
        return MarketplaceSkillImportForm(
            template_skill_key=skill.template_skill_key,
            skill_id=skill.skill_id,
            skill_name=loaded.manifest.name,
            required=skill.required,
            form=self.skill_service.get_install_schema(skill.skill_id, "", user_email),
        )

    def _validate_skill_configs(
        self,
        template: MarketplaceAgentTemplate,
        skill_configs: dict[str, dict[str, Any]],
        user_email: str,
    ) -> None:
        template_skill_keys = {skill.template_skill_key for skill in template.skills}
        unknown = set(skill_configs) - template_skill_keys
        if unknown:
            raise ValueError(f"Unknown skill config key(s): {', '.join(sorted(unknown))}")

        for skill in template.skills:
            if skill.required and skill.template_skill_key not in skill_configs and not skill.default_config:
                raise ValueError(f"Missing config for {skill.display_name or skill.skill_id}")
            self.skill_service.validate_install_config(
                skill.skill_id,
                user_email,
                self._merged_skill_config(skill, skill_configs),
            )

    def _merged_skill_config(
        self,
        skill: MarketplaceAgentSkillTemplate,
        skill_configs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            **skill.default_config,
            **skill_configs.get(skill.template_skill_key, {}),
        }

    def _validate_provider_model(self, user_email: str, provider: str, model: str | None) -> None:
        values = {"agent_provider": provider}
        if model:
            values["agent_model"] = model
        validate_form_options(
            get_create_agent_form().form_inputs,
            values,
            FormOptionsContext(user_email=user_email),
        )

    def _published_skill_templates(
        self,
        agent_id: str,
        included_skill_ids: list[str],
    ) -> list[MarketplaceAgentSkillTemplate]:
        installed = self.skill_repository.list_by_agent(agent_id)
        included = set(included_skill_ids)
        selected = [
            skill
            for skill in installed
            if skill.installed_skill_id in included or skill.skill_id in included
        ]
        return [self._skill_template_from_installed(skill) for skill in selected]

    def _skill_template_from_installed(self, skill: AgentSkill) -> MarketplaceAgentSkillTemplate:
        loaded = self.skill_service.registry.get(skill.skill_id)
        enabled_on_import = not (loaded.manifest.requires_oauth if loaded else False)
        return MarketplaceAgentSkillTemplate(
            template_skill_key=skill.installed_skill_id or skill.skill_id,
            skill_id=skill.skill_id,
            display_name=skill.skill_name,
            description=skill.skill_description,
            required=True,
            enabled_on_import=enabled_on_import,
            default_config=self._safe_default_config(skill),
        )

    def _safe_default_config(self, skill: AgentSkill) -> dict[str, Any]:
        return {
            key: value
            for key, value in skill.config.items()
            if key not in set(skill.secret_fields)
        }


def get_agent_marketplace_service() -> AgentMarketplaceService:
    return AgentMarketplaceService()
