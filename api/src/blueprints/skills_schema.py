"""Blueprint skill entries generated from the skill manifests.

Nothing about any particular skill is written here: each `manifest.yml` in the registry becomes one
variant with that skill's real config fields, so the blueprint schema follows the skills as they
change. Plan and apply still run the registry's own install checks; these variants are for
authoring and early, precise errors.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field, create_model

import src.form_models as form_models
from src.blueprints.spec import AVAILABLE_TO_DESCRIPTION, AgentSpec, SharedAudience
from src.skills.models import LoadedSkill
from src.skills.registry import SkillRegistry, get_skill_registry, is_secret_input

STRICT = ConfigDict(extra="forbid")

#: Option sources whose values are agents, so a blueprint may name an Agent resource there instead of an id.
AGENT_OPTION_SOURCES = frozenset({"agents"})


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

    @property
    def agent_fields(self) -> list[str]:
        """Settings that name one of the person's agents: an Agent in the blueprint, or an agent id."""
        return [
            field.name for field in self.skill.manifest.form
            if field.options_source and field.options_source.type in AGENT_OPTION_SOURCES
        ]

    @property
    def required_secrets(self) -> list[form_models.FormInput]:
        return [
            field for field in self.skill.manifest.form
            if field.name in self.secret_fields and not field.is_optional and field.value is None
        ]

    @property
    def required_settings(self) -> list[form_models.FormInput]:
        return [
            field for field in self.skill.manifest.form
            if field.name not in self.secret_fields and not field.is_optional and field.value is None
        ]

    @property
    def builder_settings(self) -> list[form_models.FormInput]:
        """Required settings Ada writes: the design of the build, which she knows from the request."""
        return [field for field in self.required_settings if supplied_by(field, self) == Supplier.BUILDER]

    @property
    def person_settings(self) -> list[form_models.FormInput]:
        """Required settings only the person knows; the system asks them in a form."""
        return [field for field in self.required_settings if supplied_by(field, self) == Supplier.PERSON]

    @property
    def setup(self) -> "SkillSetup":
        return setup_for(self)


# --- What a skill needs before it can work ----------------------------------------------------------------


class SkillSetup(str, Enum):
    """What has to happen before a skill works, easiest first. Read from the manifest, never listed per skill."""

    #: Nothing from the person: add it (with any settings Ada writes) and it works.
    READY = "ready"
    #: Settings only the person knows, such as recipients or a site address. The system asks them in a form.
    SETTINGS = "settings"
    #: An account the person connects (Google sign-in). Buildable once it's connected.
    ACCOUNT = "account"
    #: A secret such as an API key, which can't go in a blueprint yet.
    SECRETS = "secrets"


class SetupRule(Protocol):
    setup: SkillSetup

    def applies(self, variant: SkillVariant) -> bool: ...


class NeedsSecrets:
    setup = SkillSetup.SECRETS

    def applies(self, variant: SkillVariant) -> bool:
        return bool(variant.required_secrets)


class NeedsAccount:
    setup = SkillSetup.ACCOUNT

    def applies(self, variant: SkillVariant) -> bool:
        manifest = variant.skill.manifest
        return manifest.requires_oauth or bool(manifest.connectors)


class NeedsSettings:
    setup = SkillSetup.SETTINGS

    def applies(self, variant: SkillVariant) -> bool:
        return bool(variant.person_settings)


class NeedsNothing:
    setup = SkillSetup.READY

    def applies(self, variant: SkillVariant) -> bool:
        return True


#: The hardest need decides: a skill with settings and a secret is a secrets skill.
SETUP_RULES: tuple[SetupRule, ...] = (NeedsSecrets(), NeedsAccount(), NeedsSettings(), NeedsNothing())


def setup_for(variant: SkillVariant) -> SkillSetup:
    return next(rule.setup for rule in SETUP_RULES if rule.applies(variant))


# --- Who supplies a setting -------------------------------------------------------------------------------


class Supplier(str, Enum):
    #: Ada, from the person's request: which agent to call, when to use it. Asking would be asking them to design.
    BUILDER = "builder"
    #: The person: facts only they know, such as where emails go.
    PERSON = "person"


class SupplierRule(Protocol):
    supplier: Supplier

    def applies(self, field: form_models.FormInput, variant: SkillVariant) -> bool: ...


class Declared:
    """`attr.supplied_by` in the manifest, when the skill author says. It wins over every other rule."""

    def __init__(self, supplier: Supplier):
        self.supplier = supplier

    def applies(self, field: form_models.FormInput, variant: SkillVariant) -> bool:
        return (field.attr or {}).get("supplied_by") == self.supplier.value


class NamesAnAgent:
    """Which agent a skill works with is the shape of the build."""

    supplier = Supplier.BUILDER

    def applies(self, field: form_models.FormInput, variant: SkillVariant) -> bool:
        return field.name in variant.agent_fields


class GuidesTheModel:
    """Text the agent reads at run time ("when should this agent be invoked?") is instructions, which Ada writes."""

    supplier = Supplier.BUILDER

    def applies(self, field: form_models.FormInput, variant: SkillVariant) -> bool:
        return (field.attr or {}).get("expose_to_runtime") == "true"


class EverythingElse:
    supplier = Supplier.PERSON

    def applies(self, field: form_models.FormInput, variant: SkillVariant) -> bool:
        return True


SUPPLIER_RULES: tuple[SupplierRule, ...] = (
    Declared(Supplier.BUILDER),
    Declared(Supplier.PERSON),
    NamesAnAgent(),
    GuidesTheModel(),
    EverythingElse(),
)


def supplied_by(field: form_models.FormInput, variant: SkillVariant) -> Supplier:
    return next(rule.supplier for rule in SUPPLIER_RULES if rule.applies(field, variant))


def agent_settings(spec: AgentSpec, registry: Optional[SkillRegistry] = None) -> list[tuple[int, str, str]]:
    """(entry index, setting, value) for every skill setting on this agent that names an agent."""
    variants = skill_variants(registry)
    found = []
    for index, entry in enumerate(spec.skills):
        variant = variants.get(entry.id)
        for field_name in variant.agent_fields if variant else []:
            value = (entry.config or {}).get(field_name)
            if isinstance(value, str) and value:
                found.append((index, field_name, value))
    return found


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
