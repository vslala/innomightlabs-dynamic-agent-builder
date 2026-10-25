from __future__ import annotations

import builtins
import hashlib
import importlib
import inspect
import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional, cast

import yaml  # type: ignore[import-untyped,unused-ignore]

import src.form_models as form_models
from src.form_validation import validate_submission
from src.skills.disclosure import SUGGESTION_LIMIT, search_actions
from src.skills.models import LoadedSkill, SkillActionManifest, SkillManifest

log = logging.getLogger(__name__)


class SkillRegistry:
    """Filesystem-backed skill registry loaded from src/skills/*/manifest.yml."""

    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir or Path(__file__).resolve().parent
        self._loaded: dict[str, LoadedSkill] = {}
        self.reload()

    def reload(self) -> None:
        loaded: dict[str, LoadedSkill] = {}
        core: dict[str, LoadedSkill] = {}
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
                if manifest.id in loaded or manifest.id in core:
                    raise ValueError(f"duplicate skill id '{manifest.id}'")

                (core if manifest.core else loaded)[manifest.id] = LoadedSkill(manifest=manifest, folder_name=folder.name)
            except Exception as e:
                log.warning("Skipping invalid skill manifest %s: %s", manifest_path, e)

        self._loaded = loaded
        self._core = core
        #: Changes whenever a manifest does; caches built from the manifests key on it.
        self.version = hashlib.sha256(
            json.dumps(
                [every.manifest.model_dump(mode="json") for every in sorted([*loaded.values(), *core.values()], key=lambda s: s.manifest.id)],
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:16]
        log.info("Loaded %d skills and %d core skills from %s", len(loaded), len(core), self.root_dir)

    def list(self) -> list[LoadedSkill]:
        """The installable skills: what the catalog offers, agents install and automations enable."""
        return sorted(self._loaded.values(), key=lambda s: s.manifest.name.lower())

    def get(self, skill_id: str) -> Optional[LoadedSkill]:
        """An installable skill. A core skill isn't one: its actions are core tools (`core()`)."""
        return self._loaded.get(skill_id)

    def core_skills(self) -> builtins.list[LoadedSkill]:
        return sorted(self._core.values(), key=lambda s: s.manifest.id)

    def core(self, skill_id: str) -> Optional[LoadedSkill]:
        """A core skill: a manifest whose actions every agent gets as tools of a family, never installed."""
        return self._core.get(skill_id)

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

        return {input_def.name for input_def in loaded.manifest.form if is_secret_input(input_def)}

    def validate_config(self, skill_id: str, config: dict[str, Any]) -> dict[str, Any]:
        loaded = self.get(skill_id)
        if not loaded:
            raise ValueError(f"Unknown skill: {skill_id}")

        for input_def in loaded.manifest.form:
            # Skill config is saved as JSON with the install; there is nowhere to keep an upload
            if input_def.input_type == form_models.FormInputType.FILE_UPLOAD:
                raise ValueError(f"Unsupported form input type for skill config: {input_def.input_type}")

        result = validate_submission(loaded.manifest.form, config)
        if result.missing:
            raise ValueError(f"Missing required field: {result.missing[0]}")
        if result.invalid:
            raise ValueError(next(iter(result.invalid.values())))
        return result.values

    async def execute_action(
        self,
        skill_id: str,
        action_name: str,
        arguments: dict[str, Any],
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> Any:
        loaded = self.get(skill_id) or self.core(skill_id)
        if not loaded:
            raise ValueError(f"Unknown skill: {skill_id}")

        action = loaded.manifest.find_action(action_name)
        if not action:
            suggestions = [
                a.name for a in search_actions(loaded.manifest, action_name.replace("_", " "), SUGGESTION_LIMIT)
            ]
            hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
            raise ValueError(f"Skill '{skill_id}' has no action '{action_name}'.{hint}")

        # Lightweight required-field check from JSON schema. The schema rides along in the
        # error so an agent that skipped load_skill can correct itself in one retry.
        required_fields = action.input_schema.get("required", [])
        for field_name in required_fields:
            if field_name not in arguments:
                raise ValueError(
                    f"Missing required action argument: {field_name}. {_schema_hint(action)}"
                )

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
        return cast(Callable[..., Any], func)


def is_secret_input(input_def: form_models.FormInput) -> bool:
    """Stored encrypted and never shown to the model. A password input is a secret even if the manifest forgets to say so."""
    attr = input_def.attr or {}
    return (
        input_def.input_type == form_models.FormInputType.PASSWORD
        or attr.get("secret", "false").lower() == "true"
    )


def _schema_hint(action: SkillActionManifest) -> str:
    return f"Schema for '{action.name}': {json.dumps(action.input_schema, ensure_ascii=True)}"


_registry_singleton: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    global _registry_singleton
    if _registry_singleton is None:
        _registry_singleton = SkillRegistry()
    return _registry_singleton
