from __future__ import annotations

import importlib
import inspect
import logging
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

import src.form_models as form_models
from src.skills.models import LoadedSkill, SkillManifest

log = logging.getLogger(__name__)


class SkillRegistry:
    """Filesystem-backed skill registry loaded from src/skills/*/manifest.yml."""

    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir or Path(__file__).resolve().parent
        self._loaded: dict[str, LoadedSkill] = {}
        self.reload()

    def reload(self) -> None:
        loaded: dict[str, LoadedSkill] = {}
        for folder in self.root_dir.iterdir():
            if not folder.is_dir() or folder.name.startswith("__"):
                continue
            manifest_path = folder / "manifest.yml"
            if not manifest_path.exists():
                continue

            try:
                data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("manifest root must be an object")

                manifest = SkillManifest.model_validate(data)
                if manifest.id in loaded:
                    raise ValueError(f"duplicate skill id '{manifest.id}'")

                loaded[manifest.id] = LoadedSkill(manifest=manifest, folder_name=folder.name)
            except Exception as e:
                log.warning("Skipping invalid skill manifest %s: %s", manifest_path, e)

        self._loaded = loaded
        log.info("Loaded %d skills from %s", len(self._loaded), self.root_dir)

    def list(self) -> list[LoadedSkill]:
        return sorted(self._loaded.values(), key=lambda s: s.manifest.name.lower())

    def get(self, skill_id: str) -> Optional[LoadedSkill]:
        return self._loaded.get(skill_id)

    def install_form(self, skill_id: str, submit_path: str) -> form_models.Form:
        loaded = self.get(skill_id)
        if not loaded:
            raise ValueError(f"Unknown skill: {skill_id}")

        return form_models.Form(
            form_name=f"Install {loaded.manifest.name}",
            submit_path=submit_path,
            form_inputs=loaded.manifest.form,
        )

    def secret_fields(self, skill_id: str) -> set[str]:
        loaded = self.get(skill_id)
        if not loaded:
            return set()

        fields: set[str] = set()
        for input_def in loaded.manifest.form:
            attr = input_def.attr or {}
            if attr.get("secret", "false").lower() == "true":
                fields.add(input_def.name)
        return fields

    def validate_config(self, skill_id: str, config: dict[str, Any]) -> dict[str, Any]:
        loaded = self.get(skill_id)
        if not loaded:
            raise ValueError(f"Unknown skill: {skill_id}")

        normalized: dict[str, Any] = {}
        for input_def in loaded.manifest.form:
            value = config.get(input_def.name, input_def.value)
            attr = input_def.attr or {}
            optional = attr.get("optional", "false").lower() == "true"

            if value is None or value == "":
                if optional:
                    continue
                raise ValueError(f"Missing required field: {input_def.name}")

            if input_def.input_type in {
                form_models.FormInputType.TEXT,
                form_models.FormInputType.TEXT_AREA,
                form_models.FormInputType.PASSWORD,
                form_models.FormInputType.SELECT,
                form_models.FormInputType.CHOICE,
            }:
                normalized[input_def.name] = str(value)
            else:
                raise ValueError(f"Unsupported form input type for skill config: {input_def.input_type}")

            if input_def.input_type in {form_models.FormInputType.SELECT, form_models.FormInputType.CHOICE}:
                allowed = set(input_def.values or [])
                if input_def.options:
                    allowed.update(opt.value for opt in input_def.options)
                if allowed and normalized[input_def.name] not in allowed:
                    raise ValueError(
                        f"Invalid value for {input_def.name}. Allowed: {', '.join(sorted(allowed))}"
                    )

        return normalized

    async def execute_action(
        self,
        skill_id: str,
        action_name: str,
        arguments: dict[str, Any],
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> Any:
        loaded = self.get(skill_id)
        if not loaded:
            raise ValueError(f"Unknown skill: {skill_id}")

        action = next((a for a in loaded.manifest.actions if a.name == action_name), None)
        if not action:
            raise ValueError(f"Skill '{skill_id}' has no action '{action_name}'")

        # Lightweight required-field check from JSON schema
        required_fields = action.input_schema.get("required", [])
        for field_name in required_fields:
            if field_name not in arguments:
                raise ValueError(f"Missing required action argument: {field_name}")

        func = self._resolve_handler(loaded.folder_name, action.handler)
        result = func(arguments=arguments, config=config, context=context)
        if inspect.isawaitable(result):
            return await result
        return result

    def _resolve_handler(
        self,
        folder_name: str,
        handler: str,
    ) -> Callable[..., Any]:
        module_part: str
        function_name: str

        if ":" in handler:
            module_part, function_name = handler.split(":", 1)
        else:
            module_part, function_name = handler.rsplit(".", 1)

        module_path = module_part
        if not module_path.startswith("src."):
            module_path = f"src.skills.{folder_name}.{module_path}"

        module = importlib.import_module(module_path)
        func = getattr(module, function_name, None)
        if not callable(func):
            raise ValueError(f"Invalid action handler: {handler}")
        return func


_registry_singleton: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    global _registry_singleton
    if _registry_singleton is None:
        _registry_singleton = SkillRegistry()
    return _registry_singleton
