from __future__ import annotations

import json
from typing import Any, Optional

import src.form_models as form_models
from src.connectors.service import ConnectorService, connector_id_for_provider, get_connector_service
from src.form_options import FormOptionsContext, hydrate_form_options, validate_form_options
from src.skills.identity import installed_skill_id_for
from src.skills.lifecycle import SkillLifecycleRunner
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository
from src.skills.models import (
    AgentSkill,
    InstalledSkillResponse,
    SkillCatalogItemResponse,
    SkillConnectorDependency,
)
from src.skills.oauth_providers import get_skill_oauth_provider
from src.skills.registry import SkillRegistry, get_skill_registry
from src.skills.repository import AgentSkillRepository, get_agent_skill_repository


class SkillService:
    def __init__(
        self,
        registry: Optional[SkillRegistry] = None,
        repository: Optional[AgentSkillRepository] = None,
        provider_settings_repository: Optional[ProviderSettingsRepository] = None,
        connector_service: Optional[ConnectorService] = None,
        lifecycle_runner: Optional[SkillLifecycleRunner] = None,
    ):
        self.registry = registry or get_skill_registry()
        self.repository = repository or get_agent_skill_repository()
        self.provider_settings_repository = provider_settings_repository or get_provider_settings_repository()
        self.connector_service = connector_service or get_connector_service()
        self.lifecycle_runner = lifecycle_runner or SkillLifecycleRunner(self.registry)

    def list_catalog(self, user_email: str | None = None) -> list[SkillCatalogItemResponse]:
        items: list[SkillCatalogItemResponse] = []
        for loaded in self.registry.list():
            oauth_provider_name = loaded.manifest.oauth_provider_name if loaded.manifest.requires_oauth else None
            connector_dependencies = list(loaded.manifest.connectors)
            connector_id = connector_id_for_provider(oauth_provider_name)
            if connector_id and not any(item.connector_id == connector_id for item in connector_dependencies):
                connector_dependencies.append(SkillConnectorDependency(connector_id=connector_id))
            manifest_for_status = loaded.manifest.model_copy(
                update={"connectors": connector_dependencies}
            )
            oauth_connected: bool | None = None
            oauth_provider = get_skill_oauth_provider(oauth_provider_name)
            if oauth_provider_name and user_email:
                oauth_connected = (
                    self.provider_settings_repository.find_by_provider(user_email, oauth_provider_name) is not None
                )
            items.append(
                SkillCatalogItemResponse(
                    skill_id=loaded.manifest.id,
                    namespace=loaded.manifest.namespace,
                    name=loaded.manifest.name,
                    description=loaded.manifest.description,
                    action_names=[a.name for a in loaded.manifest.actions],
                    has_form=bool(loaded.manifest.form),
                    requires_oauth=loaded.manifest.requires_oauth,
                    oauth_provider_name=oauth_provider_name,
                    oauth_connected=oauth_connected,
                    oauth_start_path=oauth_provider.start_path if oauth_provider else None,
                    connectors=self.connector_service.statuses_for_manifest(
                        manifest_for_status,
                        user_email,
                    ),
                    available=not self.connector_service.missing_required_connectors(
                        manifest_for_status,
                        user_email,
                    )
                    if user_email
                    else not manifest_for_status.connectors,
                    repeatable=loaded.manifest.repeatable,
                )
            )
        return items

    def get_install_schema(self, skill_id: str, submit_path: str, user_email: str | None = None) -> form_models.Form:
        form = self.registry.install_form(skill_id, submit_path)
        if not user_email:
            return form
        return hydrate_form_options(
            form,
            FormOptionsContext(user_email=user_email),
        )

    def install_skill(
        self,
        *,
        agent_id: str,
        skill_id: str,
        user_email: str,
        raw_config: dict[str, Any],
    ) -> AgentSkill:
        loaded = self.registry.get(skill_id)
        if not loaded:
            raise ValueError(f"Unknown skill: {skill_id}")

        if loaded.manifest.requires_oauth and loaded.manifest.oauth_provider_name:
            provider_settings = self.provider_settings_repository.find_by_provider(
                user_email,
                loaded.manifest.oauth_provider_name,
            )
            if not provider_settings:
                raise ValueError(
                    f"{loaded.manifest.name} requires a connected {loaded.manifest.oauth_provider_name} account before installation"
                )
        missing_connectors = self.connector_service.missing_required_connectors(loaded.manifest, user_email)
        if missing_connectors:
            raise ValueError(
                f"{loaded.manifest.name} requires connected connector(s): {', '.join(missing_connectors)}"
            )

        normalized = self.registry.validate_config(skill_id, raw_config)
        validate_form_options(
            loaded.manifest.form,
            normalized,
            FormOptionsContext(user_email=user_email),
        )
        secret_fields = self.registry.secret_fields(skill_id)
        plain_config = {k: v for k, v in normalized.items() if k not in secret_fields}
        secret_config = {k: v for k, v in normalized.items() if k in secret_fields}
        installed_skill_id = installed_skill_id_for(loaded.manifest, normalized)

        return self.repository.upsert_with_config(
            agent_id=agent_id,
            installed_skill_id=installed_skill_id,
            skill_id=skill_id,
            namespace=loaded.manifest.namespace,
            skill_name=loaded.manifest.name,
            skill_description=loaded.manifest.description,
            enabled=True,
            installed_by=user_email,
            plain_config=plain_config,
            secret_config=secret_config,
            secret_fields=sorted(secret_fields),
        )

    def list_installed(self, agent_id: str) -> list[InstalledSkillResponse]:
        installed = self.repository.list_by_agent(agent_id)
        return [self.to_installed_response(item) for item in installed]

    def to_installed_response(self, item: AgentSkill) -> InstalledSkillResponse:
        loaded = self.registry.get(item.skill_id)
        requires_oauth = loaded.manifest.requires_oauth if loaded else False
        oauth_provider_name = loaded.manifest.oauth_provider_name if loaded and loaded.manifest.requires_oauth else None
        return InstalledSkillResponse(
            installed_skill_id=item.installed_skill_id or item.skill_id,
            skill_id=item.skill_id,
            namespace=item.namespace,
            name=item.skill_name,
            description=item.skill_description,
            enabled=item.enabled,
            installed_at=item.installed_at,
            updated_at=item.updated_at,
            config=item.config,
            secret_fields=item.secret_fields,
            requires_oauth=requires_oauth,
            oauth_provider_name=oauth_provider_name,
        )

    def uninstall(
        self,
        *,
        agent_id: str,
        installed_skill_id: str,
        user_email: str,
        disconnect_oauth: bool = False,
    ) -> bool:
        existing = self.repository.find_by_id(agent_id, installed_skill_id)
        if existing:
            self.lifecycle_runner.run_skill_delete(
                skill_id=existing.skill_id,
                installed_skill_id=existing.installed_skill_id or existing.skill_id,
                owner_email=user_email,
                config=self.repository.get_runtime_config(existing),
                metadata={
                    "agent_id": agent_id,
                    "installed_skill": existing.model_dump(mode="json"),
                    "disconnect_oauth": disconnect_oauth,
                },
            )
        deleted = self.repository.delete(agent_id, installed_skill_id)
        if disconnect_oauth:
            loaded = self.registry.get(existing.skill_id) if existing else self.registry.get(installed_skill_id)
            oauth_provider_name = loaded.manifest.oauth_provider_name if loaded and loaded.manifest.requires_oauth else None
            if oauth_provider_name:
                self.provider_settings_repository.delete(user_email, oauth_provider_name)
        return deleted

    def update_installed(
        self,
        *,
        agent_id: str,
        installed_skill_id: str,
        enabled: bool | None,
        raw_config: dict[str, Any] | None,
    ) -> AgentSkill:
        existing = self.repository.find_by_id(agent_id, installed_skill_id)
        if not existing:
            raise ValueError("Skill not installed for this agent")

        loaded = self.registry.get(existing.skill_id)
        if not loaded:
            raise ValueError("Skill not available")

        final_enabled = existing.enabled if enabled is None else enabled
        plain_config = dict(existing.config)
        secret_config: dict[str, Any] = {}

        if existing.encrypted_secrets:
            decrypted = self.repository.get_runtime_config(existing)
            for field_name in existing.secret_fields:
                if field_name in decrypted:
                    secret_config[field_name] = decrypted[field_name]

        if raw_config is not None:
            # Merge update payload with existing runtime config, validate complete shape, then split
            merged = self.repository.get_runtime_config(existing)
            merged.update(raw_config)
            normalized = self.registry.validate_config(existing.skill_id, merged)
            validate_form_options(
                loaded.manifest.form,
                normalized,
                FormOptionsContext(user_email=existing.installed_by),
            )
            next_installed_skill_id = installed_skill_id_for(loaded.manifest, normalized)
            if next_installed_skill_id != existing.installed_skill_id:
                raise ValueError("Repeatable skill identity fields cannot be changed")
            secret_fields = self.registry.secret_fields(existing.skill_id)
            plain_config = {k: v for k, v in normalized.items() if k not in secret_fields}
            secret_config = {k: v for k, v in normalized.items() if k in secret_fields}
            secret_field_list = sorted(secret_fields)
        else:
            secret_field_list = existing.secret_fields

        return self.repository.upsert_with_config(
            agent_id=agent_id,
            installed_skill_id=existing.installed_skill_id or existing.skill_id,
            skill_id=existing.skill_id,
            namespace=loaded.manifest.namespace,
            skill_name=loaded.manifest.name,
            skill_description=loaded.manifest.description,
            enabled=final_enabled,
            installed_by=existing.installed_by,
            plain_config=plain_config,
            secret_config=secret_config,
            secret_fields=secret_field_list,
        )

class SkillRuntimeService:
    """Runtime behavior for MemGPT tool-based skill loading/execution."""

    _EXPOSE_TO_RUNTIME_ATTR = "expose_to_runtime"
    _USAGE_CONTEXT_LABEL_ATTR = "usage_context_label"
    _USAGE_CONTEXT_MAX_CHARS_ATTR = "usage_context_max_chars"
    _DEFAULT_USAGE_CONTEXT_MAX_CHARS = 600

    def __init__(
        self,
        skill_service: Optional[SkillService] = None,
        repository: Optional[AgentSkillRepository] = None,
    ):
        self.skill_service = skill_service or SkillService()
        self.repository = repository or get_agent_skill_repository()

    def list_enabled(self, agent_id: str) -> list[AgentSkill]:
        return [s for s in self.repository.list_by_agent(agent_id) if s.enabled]

    def build_skill_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "load_skill",
                "description": "Load full instructions and action contracts for an installed skill by skill_id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill_id": {"type": "string", "description": "Installed skill id to load"},
                    },
                    "required": ["skill_id"],
                },
            },
            {
                "name": "execute_skill_action",
                "description": (
                    "Execute an action from an installed skill. "
                    "IMPORTANT: pass action fields inside the `arguments` object only."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill_id": {"type": "string", "description": "Installed skill id"},
                        "action": {"type": "string", "description": "Action name defined by the skill"},
                        "arguments": {
                            "type": "object",
                            "description": (
                                "Action arguments following the action input_schema. "
                                "Example: {\"query\": \"pricing\"}"
                            ),
                        },
                    },
                    "required": ["skill_id", "action", "arguments"],
                    "additionalProperties": False,
                },
            },
        ]

    def build_system_prompt_addendum(self, enabled_skills: list[AgentSkill]) -> str:
        if not enabled_skills:
            return ""

        lines = [
            "<installed_skills>",
            "You can use skills to perform specialized tasks.",
            "Use load_skill(skill_id) before execute_skill_action when you need exact instructions or action schema.",
            "When calling execute_skill_action, put every action parameter inside the nested arguments object.",
            "If a skill exposes form fields with enums or fixed literals, use those exact values instead of HTML input types or synonyms.",
            "Do not claim that you sent, rendered, showed, or displayed a form unless you actually call execute_skill_action for that form in the same turn.",
            "If you want to give narrative text and then show a form, still make the tool call in that same turn. Narrative text alone does not render UI.",
            "When a skill offers both a built-in default form and a custom-form action, use the custom-form action whenever the requested fields or choices are not exactly the built-in default form.",
        ]
        for skill in enabled_skills:
            lines.append(
                f"- {skill.installed_skill_id or skill.skill_id}: "
                f"{skill.skill_name} - {skill.skill_description} "
                f"(skill_id: {skill.skill_id})"
            )
            for item in self._build_usage_context(skill):
                lines.append(f"  {item['label']}: {item['value']}")
        lines.append("</installed_skills>")
        return "\n".join(lines)

    async def handle_tool_call(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, Any],
        agent_id: str,
        owner_email: str,
        actor_email: str,
        actor_id: str,
        conversation_id: str,
    ) -> str:
        if tool_name == "load_skill":
            installed_skill_id = str(tool_input.get("skill_id", "")).strip()
            if not installed_skill_id:
                raise ValueError("Missing required argument: skill_id")

            installed = self._resolve_installed_skill(agent_id, installed_skill_id)
            if not installed or not installed.enabled:
                raise ValueError(f"Skill '{installed_skill_id}' is not installed/enabled for this agent")

            loaded = self.skill_service.registry.get(installed.skill_id)
            if not loaded:
                raise ValueError(f"Skill '{installed.skill_id}' is not available")

            payload = {
                "installed_skill_id": installed.installed_skill_id or installed.skill_id,
                "skill_id": loaded.manifest.id,
                "name": loaded.manifest.name,
                "description": loaded.manifest.description,
                "system_prompt": loaded.manifest.system_prompt,
                "usage_context": self._build_usage_context(installed),
                "execute_contract": {
                    "required_shape": {
                        "skill_id": installed.installed_skill_id or installed.skill_id,
                        "action": "<action_name>",
                        "arguments": "<object_matching_action_input_schema>",
                    },
                    "note": "Do not place action fields at top-level. Always nest inside arguments.",
                },
                "actions": [
                    {
                        "name": action.name,
                        "aliases": action.aliases,
                        "description": action.description,
                        "input_schema": action.input_schema,
                        "action_form": (
                            action.action_form.model_dump(mode="json", exclude_none=True)
                            if action.action_form
                            else None
                        ),
                    }
                    for action in loaded.manifest.actions
                ],
            }
            return json.dumps(payload, ensure_ascii=True)

        if tool_name == "execute_skill_action":
            installed_skill_id = str(tool_input.get("skill_id", "")).strip()
            action_name = str(tool_input.get("action", "")).strip()
            arguments = tool_input.get("arguments")
            if not isinstance(arguments, dict):
                raise ValueError("'arguments' must be an object")
            if not installed_skill_id or not action_name:
                raise ValueError("Missing required arguments: skill_id and action")

            installed = self._resolve_installed_skill(agent_id, installed_skill_id)
            if not installed or not installed.enabled:
                raise ValueError(f"Skill '{installed_skill_id}' is not installed/enabled for this agent")

            config = self.repository.get_runtime_config(installed)
            result = await self.skill_service.registry.execute_action(
                skill_id=installed.skill_id,
                action_name=action_name,
                arguments=arguments,
                config=config,
                context={
                    "agent_id": agent_id,
                    "owner_email": owner_email,
                    "actor_email": actor_email,
                    "actor_id": actor_id,
                    "conversation_id": conversation_id,
                },
            )
            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=True)

        raise ValueError(f"Unknown skill runtime tool: {tool_name}")

    def _resolve_installed_skill(self, agent_id: str, requested_id: str) -> AgentSkill | None:
        installed = self.repository.find_by_id(agent_id, requested_id)
        if installed:
            return installed

        matches = [
            item
            for item in self.repository.list_by_agent(agent_id)
            if item.skill_id == requested_id and item.enabled
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            ids = ", ".join(sorted(item.installed_skill_id or item.skill_id for item in matches))
            raise ValueError(
                f"Skill '{requested_id}' has multiple installed instances. Use one of: {ids}"
            )
        return None

    def _build_usage_context(self, skill: AgentSkill) -> list[dict[str, str]]:
        loaded = self.skill_service.registry.get(skill.skill_id)
        if not loaded:
            return []

        summary: list[dict[str, str]] = []
        for input_def in loaded.manifest.form:
            attr = input_def.attr or {}
            if attr.get("secret", "false").lower() == "true":
                continue
            if attr.get(self._EXPOSE_TO_RUNTIME_ATTR, "false").lower() != "true":
                continue

            value = skill.config.get(input_def.name)
            rendered = self._render_usage_context_value(value, attr)
            if not rendered:
                continue

            summary.append(
                {
                    "name": input_def.name,
                    "label": attr.get(self._USAGE_CONTEXT_LABEL_ATTR) or input_def.label,
                    "value": rendered,
                }
            )
        return summary

    def _render_usage_context_value(self, value: Any, attr: dict[str, str]) -> str:
        if value is None or value == "":
            return ""

        if isinstance(value, str):
            rendered = value.strip()
        else:
            rendered = json.dumps(value, ensure_ascii=True, sort_keys=True)

        if not rendered:
            return ""

        max_chars = self._parse_positive_int(
            attr.get(self._USAGE_CONTEXT_MAX_CHARS_ATTR),
            self._DEFAULT_USAGE_CONTEXT_MAX_CHARS,
        )
        if len(rendered) <= max_chars:
            return rendered
        return f"{rendered[: max_chars - 1].rstrip()}..."

    @staticmethod
    def _parse_positive_int(value: str | None, default: int) -> int:
        if not value:
            return default
        try:
            parsed = int(value)
        except ValueError:
            return default
        return parsed if parsed > 0 else default


def get_skill_service() -> SkillService:
    return SkillService()
