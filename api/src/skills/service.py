from __future__ import annotations

import json
from typing import Any, Optional

import src.form_models as form_models
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository
from src.skills.models import AgentSkill, InstalledSkillResponse, SkillCatalogItemResponse
from src.skills.registry import SkillRegistry, get_skill_registry
from src.skills.repository import AgentSkillRepository, get_agent_skill_repository


class SkillService:
    def __init__(
        self,
        registry: Optional[SkillRegistry] = None,
        repository: Optional[AgentSkillRepository] = None,
        provider_settings_repository: Optional[ProviderSettingsRepository] = None,
    ):
        self.registry = registry or get_skill_registry()
        self.repository = repository or get_agent_skill_repository()
        self.provider_settings_repository = provider_settings_repository or get_provider_settings_repository()

    def list_catalog(self, user_email: str | None = None) -> list[SkillCatalogItemResponse]:
        items: list[SkillCatalogItemResponse] = []
        for loaded in self.registry.list():
            oauth_provider_name = loaded.manifest.oauth_provider_name if loaded.manifest.requires_oauth else None
            oauth_connected: bool | None = None
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
                )
            )
        return items

    def get_install_schema(self, skill_id: str, submit_path: str) -> form_models.Form:
        return self.registry.install_form(skill_id, submit_path)

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

        normalized = self.registry.validate_config(skill_id, raw_config)
        secret_fields = self.registry.secret_fields(skill_id)
        plain_config = {k: v for k, v in normalized.items() if k not in secret_fields}
        secret_config = {k: v for k, v in normalized.items() if k in secret_fields}

        return self.repository.upsert_with_config(
            agent_id=agent_id,
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
        return [
            InstalledSkillResponse(
                skill_id=item.skill_id,
                namespace=item.namespace,
                name=item.skill_name,
                description=item.skill_description,
                enabled=item.enabled,
                installed_at=item.installed_at,
                updated_at=item.updated_at,
                config=item.config,
                secret_fields=item.secret_fields,
            )
            for item in installed
        ]

    def uninstall(self, agent_id: str, skill_id: str) -> bool:
        return self.repository.delete(agent_id, skill_id)

    def update_installed(
        self,
        *,
        agent_id: str,
        skill_id: str,
        enabled: bool | None,
        raw_config: dict[str, Any] | None,
    ) -> AgentSkill:
        existing = self.repository.find_by_id(agent_id, skill_id)
        if not existing:
            raise ValueError("Skill not installed for this agent")

        loaded = self.registry.get(skill_id)
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
            normalized = self.registry.validate_config(skill_id, merged)
            secret_fields = self.registry.secret_fields(skill_id)
            plain_config = {k: v for k, v in normalized.items() if k not in secret_fields}
            secret_config = {k: v for k, v in normalized.items() if k in secret_fields}
            secret_field_list = sorted(secret_fields)
        else:
            secret_field_list = existing.secret_fields

        return self.repository.upsert_with_config(
            agent_id=agent_id,
            skill_id=skill_id,
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
        ]
        for skill in enabled_skills:
            lines.append(f"- {skill.skill_id}: {skill.skill_name} - {skill.skill_description}")
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
            skill_id = str(tool_input.get("skill_id", "")).strip()
            if not skill_id:
                raise ValueError("Missing required argument: skill_id")

            installed = self.repository.find_by_id(agent_id, skill_id)
            if not installed or not installed.enabled:
                raise ValueError(f"Skill '{skill_id}' is not installed/enabled for this agent")

            loaded = self.skill_service.registry.get(skill_id)
            if not loaded:
                raise ValueError(f"Skill '{skill_id}' is not available")

            payload = {
                "skill_id": loaded.manifest.id,
                "name": loaded.manifest.name,
                "description": loaded.manifest.description,
                "system_prompt": loaded.manifest.system_prompt,
                "execute_contract": {
                    "required_shape": {
                        "skill_id": loaded.manifest.id,
                        "action": "<action_name>",
                        "arguments": "<object_matching_action_input_schema>",
                    },
                    "note": "Do not place action fields at top-level. Always nest inside arguments.",
                },
                "actions": [
                    {
                        "name": action.name,
                        "description": action.description,
                        "input_schema": action.input_schema,
                    }
                    for action in loaded.manifest.actions
                ],
            }
            return json.dumps(payload, ensure_ascii=True)

        if tool_name == "execute_skill_action":
            skill_id = str(tool_input.get("skill_id", "")).strip()
            action_name = str(tool_input.get("action", "")).strip()
            arguments = tool_input.get("arguments")
            if not isinstance(arguments, dict):
                raise ValueError("'arguments' must be an object")
            if not skill_id or not action_name:
                raise ValueError("Missing required arguments: skill_id and action")

            installed = self.repository.find_by_id(agent_id, skill_id)
            if not installed or not installed.enabled:
                raise ValueError(f"Skill '{skill_id}' is not installed/enabled for this agent")

            config = self.repository.get_runtime_config(installed)
            result = await self.skill_service.registry.execute_action(
                skill_id=skill_id,
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


def get_skill_service() -> SkillService:
    return SkillService()
