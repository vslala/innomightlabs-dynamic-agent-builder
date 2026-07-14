from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from src.automation_marketplace.models import (
    ArchiveMarketplaceAutomationResponse,
    ImportedMarketplaceAutomationSkillResponse,
    ImportMarketplaceAutomationRequest,
    ImportMarketplaceAutomationResponse,
    MarketplaceAutomationImportSession,
    MarketplaceAutomationImportSessionResponse,
    MarketplaceAutomationDetailResponse,
    MarketplaceAutomationEdgeTemplate,
    MarketplaceAutomationImportPlanInfo,
    MarketplaceAutomationImportPlanResponse,
    MarketplaceAutomationNodeTemplate,
    MarketplaceAutomationSkillImportForm,
    MarketplaceAutomationSkillTemplate,
    MarketplaceAutomationStatus,
    MarketplaceAutomationSummaryResponse,
    MarketplaceAutomationTemplate,
    PublishMarketplaceAutomationRequest,
    PublishMarketplaceAutomationResponse,
    SaveMarketplaceAutomationImportSessionRequest,
)
from src.automation_marketplace.placeholders import (
    MarketplacePlaceholderRenderer,
    PlaceholderContext,
)
from src.automation_marketplace.repository import (
    AutomationMarketplaceRepository,
    get_automation_marketplace_repository,
)
from src.automations.models import (
    Automation,
    AutomationActionType,
    AutomationEdge,
    AutomationNode,
    AutomationNodeType,
    AutomationSkill,
    AutomationStatus,
)
from src.automations.repository import AutomationRepository
from src.form_options import FormOptionsContext, hydrate_form_options
from src.form_models import Form

if TYPE_CHECKING:
    from src.automations.service import AutomationService


T = TypeVar("T")


@dataclass(frozen=True)
class _TemplateVersionPlan:
    version: int
    parent_template_id: str | None
    previous_latest: MarketplaceAutomationTemplate | None = None


@dataclass(frozen=True)
class _InstalledTemplateSkill:
    template: MarketplaceAutomationSkillTemplate
    installed: AutomationSkill


class AutomationMarketplaceService:
    def __init__(
        self,
        repository: AutomationMarketplaceRepository | None = None,
        automation_repository: AutomationRepository | None = None,
        automation_service: AutomationService | None = None,
        placeholder_renderer: MarketplacePlaceholderRenderer | None = None,
    ):
        self.repository = repository or get_automation_marketplace_repository()
        self.automation_repository = automation_repository or AutomationRepository()
        if automation_service is None:
            from src.automations.service import AutomationService

            automation_service = AutomationService(repo=self.automation_repository)
        self.automation_service = automation_service
        self.placeholder_renderer = placeholder_renderer or MarketplacePlaceholderRenderer()

    def list_automations(
        self,
        *,
        query: str | None = None,
        limit: int = 20,
    ) -> list[MarketplaceAutomationSummaryResponse]:
        return [
            template.to_summary_response()
            for template in self.repository.list_latest_published(query=query, limit=limit)
        ]

    def get_automation(self, template_id: str) -> MarketplaceAutomationDetailResponse:
        return self._published_template(template_id).to_detail_response()

    def get_import_plan(
        self,
        *,
        template_id: str,
        user_email: str,
    ) -> MarketplaceAutomationImportPlanResponse:
        template = self._published_template(template_id)
        return MarketplaceAutomationImportPlanResponse(
            template_id=template.template_id,
            automation=MarketplaceAutomationImportPlanInfo(
                default_title=template.automation_title,
                description=template.automation_description,
                node_count=len(template.nodes),
                edge_count=len(template.edges),
            ),
            skill_forms=[self._skill_import_form(skill, user_email) for skill in template.skills],
            input_form=Form(
                form_name="Automation Inputs",
                submit_path="",
                form_inputs=[item.form_input for item in template.import_inputs],
            ),
        )

    def save_import_session(
        self,
        *,
        template_id: str,
        user_email: str,
        request: SaveMarketplaceAutomationImportSessionRequest,
    ) -> MarketplaceAutomationImportSessionResponse:
        template = self._published_template(template_id)
        session = self._load_or_create_import_session(
            template=template,
            user_email=user_email,
            session_id=request.session_id,
        )
        self._apply_import_session_update(template, session, request, user_email)
        saved = self.repository.save_import_session(session)
        return _import_session_response(saved)

    def publish_automation(
        self,
        *,
        user_email: str,
        request: PublishMarketplaceAutomationRequest,
    ) -> PublishMarketplaceAutomationResponse:
        graph = self.automation_service.get_graph(request.automation_id, user_email)
        selected_skills = self._selected_skills(request.automation_id, request.included_skill_ids)
        skill_templates = [self._skill_template_from_installed(skill) for skill in selected_skills]

        version_plan = self._version_plan(request.automation_id, user_email)
        template = self._template_from_graph(
            graph=graph,
            request=request,
            user_email=user_email,
            skill_templates=skill_templates,
            version_plan=version_plan,
        )
        self._validate_placeholders_declared(template)
        saved = self.repository.save(template)
        self._promote_latest_version(version_plan, saved)
        return PublishMarketplaceAutomationResponse(
            template_id=saved.template_id,
            status=saved.status,
            title=saved.title,
            template_version=saved.template_version,
        )

    def import_automation(
        self,
        *,
        template_id: str,
        user_email: str,
        request: ImportMarketplaceAutomationRequest,
    ) -> ImportMarketplaceAutomationResponse:
        template = self._published_template(template_id)
        resolved_request = self._resolve_import_request(template, user_email, request)
        self._validate_skill_configs(template, resolved_request.skill_configs, user_email)
        self._validate_import_inputs(template, resolved_request.import_inputs)
        saved_automation = self._create_imported_automation(template, resolved_request, user_email)
        installed: list[_InstalledTemplateSkill] = []
        try:
            installed = self._install_template_skills(
                automation_id=saved_automation.automation_id,
                template=template,
                skill_configs=resolved_request.skill_configs,
                user_email=user_email,
            )
            nodes, edges = self._imported_graph(
                automation_id=saved_automation.automation_id,
                template=template,
                installed=installed,
                import_inputs=resolved_request.import_inputs,
            )
            self.automation_service.validate_graph(nodes, edges, [], user_email, saved_automation.automation_id)
            self.automation_repository.save_graph(saved_automation.automation_id, nodes, edges, [])
        except Exception:
            self._rollback_import(saved_automation, installed, user_email)
            raise

        self._delete_import_session_if_used(request.session_id, user_email)
        self.repository.increment_import_count(template.template_id)
        return ImportMarketplaceAutomationResponse(
            automation_id=saved_automation.automation_id,
            title=saved_automation.title,
            installed_skills=[
                ImportedMarketplaceAutomationSkillResponse(
                    template_skill_key=item.template.template_skill_key,
                    installed_skill_id=self._installed_skill_id(item.installed),
                    skill_id=item.installed.skill_id,
                )
                for item in installed
            ],
            node_count=len(template.nodes),
            edge_count=len(template.edges),
        )

    def archive_automation(
        self,
        *,
        template_id: str,
        user_email: str,
    ) -> ArchiveMarketplaceAutomationResponse:
        template = self.repository.find_by_id(template_id)
        if not template or template.publisher_user_email != user_email:
            raise ValueError("Marketplace automation not found")
        template.status = MarketplaceAutomationStatus.ARCHIVED
        saved = self.repository.save(template)
        return ArchiveMarketplaceAutomationResponse(template_id=saved.template_id, status=saved.status)

    def _published_template(self, template_id: str) -> MarketplaceAutomationTemplate:
        template = self.repository.find_by_id(template_id)
        if not template or template.status != MarketplaceAutomationStatus.PUBLISHED:
            raise ValueError("Marketplace automation not found")
        if template.latest_template_id and template.latest_template_id != template.template_id:
            latest = self.repository.find_by_id(template.latest_template_id)
            if latest and latest.status == MarketplaceAutomationStatus.PUBLISHED:
                return latest
        return template

    def _load_or_create_import_session(
        self,
        *,
        template: MarketplaceAutomationTemplate,
        user_email: str,
        session_id: str | None,
    ) -> MarketplaceAutomationImportSession:
        if not session_id:
            return MarketplaceAutomationImportSession(
                template_id=template.template_id,
                owner_email=user_email,
                title=template.automation_title,
                description=template.automation_description,
            )
        return self._active_import_session(template, user_email, session_id)

    def _resolve_import_request(
        self,
        template: MarketplaceAutomationTemplate,
        user_email: str,
        request: ImportMarketplaceAutomationRequest,
    ) -> ImportMarketplaceAutomationRequest:
        if not request.session_id:
            return request
        session = self._active_import_session(template, user_email, request.session_id)
        return ImportMarketplaceAutomationRequest(
            session_id=request.session_id,
            title=request.title if request.title is not None else session.title,
            description=request.description if request.description is not None else session.description,
            skill_configs={**session.skill_configs, **request.skill_configs},
            import_inputs={**session.import_inputs, **request.import_inputs},
        )

    def _active_import_session(
        self,
        template: MarketplaceAutomationTemplate,
        user_email: str,
        session_id: str,
    ) -> MarketplaceAutomationImportSession:
        session = self.repository.find_import_session(owner_email=user_email, session_id=session_id)
        if not session or session.template_id != template.template_id or session.is_expired():
            raise ValueError("Import session expired. Reopen the import form and try again.")
        return session

    def _apply_import_session_update(
        self,
        template: MarketplaceAutomationTemplate,
        session: MarketplaceAutomationImportSession,
        request: SaveMarketplaceAutomationImportSessionRequest,
        user_email: str,
    ) -> None:
        if request.title is not None:
            title = request.title.strip()
            if not title:
                raise ValueError("Automation title is required")
            session.title = title
        if request.description is not None:
            session.description = request.description.strip() or None

        if request.skill_configs:
            session.skill_configs.update(request.skill_configs)
            self._validate_partial_skill_configs(template, request.skill_configs, session.skill_configs, user_email)
        if request.import_inputs:
            session.import_inputs.update(request.import_inputs)
            self._validate_partial_import_inputs(template, request.import_inputs)

    def _version_plan(self, source_automation_id: str, user_email: str) -> _TemplateVersionPlan:
        latest = self.repository.find_latest_for_source_automation(
            source_automation_id=source_automation_id,
            publisher_user_email=user_email,
        )
        if not latest:
            return _TemplateVersionPlan(version=1, parent_template_id=None)
        return _TemplateVersionPlan(
            version=latest.template_version + 1,
            parent_template_id=latest.parent_template_id,
            previous_latest=latest,
        )

    def _template_from_graph(
        self,
        *,
        graph: Any,
        request: PublishMarketplaceAutomationRequest,
        user_email: str,
        skill_templates: list[MarketplaceAutomationSkillTemplate],
        version_plan: _TemplateVersionPlan,
    ) -> MarketplaceAutomationTemplate:
        return MarketplaceAutomationTemplate(
            title=request.title,
            template_version=version_plan.version,
            parent_template_id=version_plan.parent_template_id,
            changelog=request.changelog,
            short_description=request.short_description,
            full_description=request.full_description,
            automation_title=graph.automation.title,
            automation_description=graph.automation.description,
            nodes=[self._node_template(node, skill_templates) for node in graph.nodes],
            edges=[self._edge_template(edge) for edge in graph.edges],
            skills=skill_templates,
            import_inputs=request.import_inputs,
            source_automation_id=request.automation_id,
            publisher_user_email=user_email,
            publisher_display_name=user_email.split("@", 1)[0],
            tags=request.tags,
            status=request.status,
        )

    def _node_template(
        self,
        node: AutomationNode,
        skill_templates: list[MarketplaceAutomationSkillTemplate],
    ) -> MarketplaceAutomationNodeTemplate:
        return MarketplaceAutomationNodeTemplate(
            node_id=node.node_id,
            type=node.type,
            name=node.name,
            description=node.description,
            position=node.position,
            config=self._publish_node_config(node, skill_templates),
        )

    def _edge_template(self, edge: AutomationEdge) -> MarketplaceAutomationEdgeTemplate:
        return MarketplaceAutomationEdgeTemplate(
            edge_id=edge.edge_id,
            source_node_id=edge.source_node_id,
            target_node_id=edge.target_node_id,
            label=edge.label,
            condition=edge.condition,
        )

    def _promote_latest_version(
        self,
        version_plan: _TemplateVersionPlan,
        saved: MarketplaceAutomationTemplate,
    ) -> None:
        latest = version_plan.previous_latest
        if latest and latest.latest_template_id != saved.template_id:
            latest.latest_template_id = saved.template_id
            self.repository.save(latest)

    def _create_imported_automation(
        self,
        template: MarketplaceAutomationTemplate,
        request: ImportMarketplaceAutomationRequest,
        user_email: str,
    ) -> Automation:
        return self.automation_repository.save_automation(
            Automation(
                title=(request.title or template.automation_title).strip(),
                description=request.description if request.description is not None else template.automation_description,
                status=AutomationStatus.DRAFT,
                created_by=user_email,
            )
        )

    def _install_template_skills(
        self,
        *,
        automation_id: str,
        template: MarketplaceAutomationTemplate,
        skill_configs: dict[str, dict[str, Any]],
        user_email: str,
    ) -> list[_InstalledTemplateSkill]:
        return [
            _InstalledTemplateSkill(
                template=skill,
                installed=self.automation_service.install_skill(
                    automation_id=automation_id,
                    skill_id=skill.skill_id,
                    raw_config=self._merged_skill_config(skill, skill_configs),
                    user_email=user_email,
                    enabled=skill.enabled_on_import,
                    validate_connectors=skill.enabled_on_import,
                ),
            )
            for skill in template.skills
        ]

    def _imported_graph(
        self,
        *,
        automation_id: str,
        template: MarketplaceAutomationTemplate,
        installed: list[_InstalledTemplateSkill],
        import_inputs: dict[str, Any],
    ) -> tuple[list[AutomationNode], list[AutomationEdge]]:
        node_id_map = {node.node_id: node.node_id for node in template.nodes}
        placeholder_context = PlaceholderContext(
            skills=self._skill_placeholder_context(installed),
            inputs=import_inputs,
        )
        return (
            [
                self._imported_node(automation_id, node, node_id_map, placeholder_context)
                for node in template.nodes
            ],
            [self._imported_edge(automation_id, edge, node_id_map) for edge in template.edges],
        )

    def _skill_placeholder_context(
        self,
        installed: list[_InstalledTemplateSkill],
    ) -> dict[str, dict[str, str]]:
        return {
            item.template.template_skill_key: {
                "installed_skill_id": self._installed_skill_id(item.installed),
                "skill_id": item.installed.skill_id,
            }
            for item in installed
        }

    def _imported_node(
        self,
        automation_id: str,
        node: MarketplaceAutomationNodeTemplate,
        node_id_map: dict[str, str],
        placeholder_context: PlaceholderContext,
    ) -> AutomationNode:
        return AutomationNode(
            node_id=node_id_map[node.node_id],
            automation_id=automation_id,
            type=node.type,
            name=node.name,
            description=node.description,
            position=node.position,
            config=self.placeholder_renderer.render(node.config, placeholder_context),
        )

    def _imported_edge(
        self,
        automation_id: str,
        edge: MarketplaceAutomationEdgeTemplate,
        node_id_map: dict[str, str],
    ) -> AutomationEdge:
        return AutomationEdge(
            automation_id=automation_id,
            source_node_id=node_id_map[edge.source_node_id],
            target_node_id=node_id_map[edge.target_node_id],
            label=edge.label,
            condition=edge.condition,
        )

    def _rollback_import(
        self,
        automation: Automation,
        installed: list[_InstalledTemplateSkill],
        user_email: str,
    ) -> None:
        for item in installed:
            self.automation_repository.delete_skill(
                automation.automation_id,
                self._installed_skill_id(item.installed),
            )
        self.automation_repository.soft_delete_automation(automation.automation_id, user_email)

    def _delete_import_session_if_used(self, session_id: str | None, user_email: str) -> None:
        if session_id:
            self.repository.delete_import_session(owner_email=user_email, session_id=session_id)

    def _installed_skill_id(self, skill: AutomationSkill) -> str:
        return skill.installed_skill_id or skill.skill_id

    def _skill_import_form(
        self,
        skill: MarketplaceAutomationSkillTemplate,
        user_email: str,
    ) -> MarketplaceAutomationSkillImportForm:
        loaded = self.automation_service.skill_registry.get(skill.skill_id)
        if not loaded:
            raise ValueError(f"Unknown skill: {skill.skill_id}")
        form = hydrate_form_options(
            self.automation_service.skill_registry.install_form(skill.skill_id, ""),
            FormOptionsContext(user_email=user_email),
        )
        return MarketplaceAutomationSkillImportForm(
            template_skill_key=skill.template_skill_key,
            skill_id=skill.skill_id,
            skill_name=loaded.manifest.name,
            required=skill.required,
            form=form,
        )

    def _validate_skill_configs(
        self,
        template: MarketplaceAutomationTemplate,
        skill_configs: dict[str, dict[str, Any]],
        user_email: str,
    ) -> None:
        for skill in template.skills:
            if self._skill_config_required(skill, skill_configs):
                raise ValueError(f"Missing configuration for skill: {skill.display_name or skill.skill_id}")
            self.automation_service.validate_skill_config(
                skill_id=skill.skill_id,
                raw_config=self._merged_skill_config(skill, skill_configs),
                user_email=user_email,
                validate_connectors=skill.enabled_on_import,
            )

    def _validate_partial_skill_configs(
        self,
        template: MarketplaceAutomationTemplate,
        changed_skill_configs: dict[str, dict[str, Any]],
        all_skill_configs: dict[str, dict[str, Any]],
        user_email: str,
    ) -> None:
        skills_by_key = {skill.template_skill_key: skill for skill in template.skills}
        for key in changed_skill_configs:
            skill = _required_lookup(skills_by_key, key, "Unknown template skill")
            self.automation_service.validate_skill_config(
                skill_id=skill.skill_id,
                raw_config=self._merged_skill_config(skill, all_skill_configs),
                user_email=user_email,
                validate_connectors=skill.enabled_on_import,
            )

    def _validate_import_inputs(
        self,
        template: MarketplaceAutomationTemplate,
        values: dict[str, Any],
    ) -> None:
        for item in template.import_inputs:
            if item.required and (item.input_key not in values or _is_blank(values.get(item.input_key))):
                raise ValueError(f"Missing import input: {item.label}")

    def _validate_partial_import_inputs(
        self,
        template: MarketplaceAutomationTemplate,
        values: dict[str, Any],
    ) -> None:
        inputs_by_key = {item.input_key: item for item in template.import_inputs}
        for key, value in values.items():
            item = _required_lookup(inputs_by_key, key, "Unknown import input")
            if item.required and _is_blank(value):
                raise ValueError(f"Missing import input: {item.label}")

    def _merged_skill_config(
        self,
        skill: MarketplaceAutomationSkillTemplate,
        skill_configs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        return {**skill.default_config, **skill_configs.get(skill.template_skill_key, {})}

    def _skill_requires_config(self, skill_id: str) -> bool:
        loaded = self.automation_service.skill_registry.get(skill_id)
        return bool(loaded and loaded.manifest.form)

    def _skill_config_required(
        self,
        skill: MarketplaceAutomationSkillTemplate,
        skill_configs: dict[str, dict[str, Any]],
    ) -> bool:
        return (
            skill.required
            and self._skill_requires_config(skill.skill_id)
            and skill.template_skill_key not in skill_configs
            and not skill.default_config
        )

    def _selected_skills(
        self,
        automation_id: str,
        included_skill_ids: list[str],
    ) -> list[AutomationSkill]:
        included = set(included_skill_ids)
        skills = [
            skill
            for skill in self.automation_repository.list_skills(automation_id)
            if skill.installed_skill_id in included or skill.skill_id in included
        ]
        return skills

    def _skill_template_from_installed(self, skill: AutomationSkill) -> MarketplaceAutomationSkillTemplate:
        loaded = self.automation_service.skill_registry.get(skill.skill_id)
        return MarketplaceAutomationSkillTemplate(
            template_skill_key=skill.installed_skill_id or skill.skill_id,
            skill_id=skill.skill_id,
            display_name=skill.skill_name,
            description=skill.skill_description,
            required=True,
            enabled_on_import=not (loaded.manifest.requires_oauth if loaded else False),
            default_config=dict(skill.config),
        )

    def _publish_node_config(
        self,
        node: AutomationNode,
        skills: list[MarketplaceAutomationSkillTemplate],
    ) -> dict[str, Any]:
        if node.type != AutomationNodeType.ACTION:
            return node.config

        action_type = _enum_value(node.config.get("action_type"))
        publisher = {
            AutomationActionType.INVOKE_AGENT.value: self._publish_invoke_agent_config,
            AutomationActionType.SKILL_ACTION.value: self._publish_skill_action_config,
        }.get(action_type)
        return publisher(node, skills) if publisher else node.config

    def _publish_invoke_agent_config(
        self,
        node: AutomationNode,
        _: list[MarketplaceAutomationSkillTemplate],
    ) -> dict[str, Any]:
        agent_id = node.config.get("agent_id")
        if agent_id and not _is_input_placeholder(str(agent_id)):
            raise ValueError(
                f"Invoke-agent node '{node.name}' must use an import input placeholder for agent_id"
            )
        return node.config

    def _publish_skill_action_config(
        self,
        node: AutomationNode,
        skills: list[MarketplaceAutomationSkillTemplate],
    ) -> dict[str, Any]:
        config = dict(node.config)
        installed_skill_id = str(config.get("installed_skill_id") or config.get("skill_id") or "")
        matching = self._selected_skill_for_config(installed_skill_id, config.get("skill_id"), skills)
        if not matching:
            raise ValueError(f"Action node '{node.name}' references a skill that was not selected for publishing")
        config["skill_id"] = matching.skill_id
        config["installed_skill_id"] = f"{{{{ skills.{matching.template_skill_key}.installed_skill_id }}}}"
        return config

    def _selected_skill_for_config(
        self,
        installed_skill_id: str,
        skill_id: Any,
        skills: list[MarketplaceAutomationSkillTemplate],
    ) -> MarketplaceAutomationSkillTemplate | None:
        for skill in skills:
            if skill.template_skill_key == installed_skill_id:
                return skill

        skill_id_matches = [skill for skill in skills if skill.skill_id == skill_id]
        if len(skill_id_matches) == 1:
            return skill_id_matches[0]
        return None

    def _validate_placeholders_declared(self, template: MarketplaceAutomationTemplate) -> None:
        declared = {item.input_key for item in template.import_inputs}
        serialized_nodes = [node.config for node in template.nodes]
        missing = sorted(_find_input_placeholders(serialized_nodes) - declared)
        if missing:
            raise ValueError("Missing import input declarations: " + ", ".join(missing))


def get_automation_marketplace_service() -> AutomationMarketplaceService:
    return AutomationMarketplaceService()


def _import_session_response(
    session: MarketplaceAutomationImportSession,
) -> MarketplaceAutomationImportSessionResponse:
    return MarketplaceAutomationImportSessionResponse(
        session_id=session.session_id,
        template_id=session.template_id,
        title=session.title,
        description=session.description,
        skill_configs=session.skill_configs,
        import_inputs=session.import_inputs,
        expires_at=session.expires_at,
    )


def _find_input_placeholders(value: Any) -> set[str]:
    from src.automation_marketplace.placeholders import PLACEHOLDER_RE

    found: set[str] = set()
    if isinstance(value, str):
        for match in PLACEHOLDER_RE.finditer(value):
            if match.group(1) == "inputs":
                found.add(match.group(2))
    elif isinstance(value, list):
        for item in value:
            found.update(_find_input_placeholders(item))
    elif isinstance(value, dict):
        for item in value.values():
            found.update(_find_input_placeholders(item))
    return found


def _is_input_placeholder(value: str) -> bool:
    from src.automation_marketplace.placeholders import PLACEHOLDER_RE

    match = PLACEHOLDER_RE.fullmatch(value.strip())
    return bool(match and match.group(1) == "inputs")


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _required_lookup(items: dict[str, T], key: str, error_prefix: str) -> T:
    item = items.get(key)
    if item is None:
        raise ValueError(f"{error_prefix}: {key}")
    return item


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, dict):
        return not value
    if isinstance(value, list):
        return not value
    return False
