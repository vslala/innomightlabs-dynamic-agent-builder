"""Blueprint skill entries generated from the skill manifests.

Nothing about any particular skill is written here: each `manifest.yml` in the registry becomes one
variant with that skill's real config fields, so the blueprint schema follows the skills as they
change. Plan and apply still run the registry's own install checks; these variants are for
authoring and early, precise errors.
"""

from dataclasses import dataclass
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, create_model

import src.form_models as form_models
from src.blueprints.spec import AVAILABLE_TO_DESCRIPTION, SharedAudience
from src.skills.models import LoadedSkill
from src.skills.registry import SkillRegistry, get_skill_registry, is_secret_input

STRICT = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class SkillVariant:
    skill: LoadedSkill
    model: type[BaseModel]
    #: Install fields a blueprint can't carry; they're set on the agent's Skills tab.
    secret_fields: tuple[str, ...]

    @property
    def shareable(self) -> bool:
        return not self.skill.manifest.runs_only_for_owner

    @property
    def config_fields(self) -> list[str]:
        return [field.name for field in self.skill.manifest.form if field.name not in self.secret_fields]


def describe_field(field: form_models.FormInput) -> str:
    """The manifest's help text when it has one, otherwise the label."""
    return (field.attr or {}).get("help_text") or field.label


def config_field(field: form_models.FormInput) -> tuple[Any, Any]:
    allowed = [*(field.values or []), *(option.value for option in field.options or [])]
    annotation: Any
    if field.input_type is form_models.FormInputType.KEY_VALUE:
        annotation = dict[str, str]
    elif allowed and not field.options_source:
        annotation = Literal[tuple(allowed)]
    else:
        annotation = str
    description = describe_field(field)
    if field.options_source:
        description += f" Must be one of your {field.options_source.type.replace('_', ' ')}."
    required = not field.is_optional and field.value is None
    if not required:
        annotation = Optional[annotation]
    return annotation, Field(... if required else field.value, title=field.label, description=description)


def requirement_note(skill: LoadedSkill) -> str:
    manifest = skill.manifest
    notes = []
    if manifest.requires_oauth and manifest.oauth_provider_name:
        notes.append(f"Needs a connected {manifest.oauth_provider_name} account.")
    if manifest.connectors:
        notes.append(f"Needs connector(s): {', '.join(c.connector_id for c in manifest.connectors)}.")
    if manifest.runs_only_for_owner:
        notes.append("Uses your own accounts or access, so only you can use it.")
    return " ".join(notes)


def skill_variant(skill: LoadedSkill) -> SkillVariant:
    manifest = skill.manifest
    secret_fields = tuple(field.name for field in manifest.form if is_secret_input(field))
    config_fields = {
        field.name: config_field(field) for field in manifest.form if field.name not in secret_fields
    }
    config_model = create_model(  # type: ignore[call-overload]
        f"{manifest.id}_config",
        __config__=STRICT,
        __doc__=f"Install settings for {manifest.name}.",
        **config_fields,
    )
    config_required = any(info.is_required() for _, info in config_fields.values())
    description = " ".join(part for part in (f"{manifest.name}: {manifest.description}", requirement_note(skill)) if part)
    fields: dict[str, Any] = {
        "id": (Literal[manifest.id], Field(description=description)),
        "config": (
            config_model if config_required else Optional[config_model],
            Field(
                ... if config_required else None,
                description=f"How to set up {manifest.name} on this agent, as its install form asks.",
            ),
        ),
        "enabled": (bool, Field(True, description="Install the skill switched off when false.")),
    }
    if not manifest.runs_only_for_owner:
        fields["available_to"] = (
            list[SharedAudience],  # type: ignore[valid-type]
            Field(default_factory=list, description=AVAILABLE_TO_DESCRIPTION),
        )
    model = create_model(
        f"Skill_{manifest.id}",
        __config__=STRICT,
        __doc__=description,
        **fields,
    )
    return SkillVariant(skill=skill, model=model, secret_fields=secret_fields)


_variants_cache: dict[tuple[int, str], dict[str, SkillVariant]] = {}


def skill_variants(registry: Optional[SkillRegistry] = None) -> dict[str, SkillVariant]:
    """One variant per registered skill, rebuilt only when a manifest changes."""
    registry = registry or get_skill_registry()
    key = (id(registry), registry.version)
    if key not in _variants_cache:
        _variants_cache[key] = {
            loaded.manifest.id: skill_variant(loaded) for loaded in registry.list()
        }
    return _variants_cache[key]
