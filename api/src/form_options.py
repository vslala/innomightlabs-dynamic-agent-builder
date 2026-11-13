from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from src.accounts.owner import Owner
from src.agents.image_generation.capabilities import ImageCapability
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.form_models import Form, FormInput, SelectOption
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository

if TYPE_CHECKING:
    from src.llm.models import ModelInfo
    from src.llm.providers.provider import Provider
    from src.settings.models import ProviderSettings

log = logging.getLogger(__name__)


class FormOptionSourceType:
    AGENTS = "agents"
    #: The knowledge bases the member owns.
    KNOWLEDGE_BASES = "knowledge_bases"
    KRISHNA_MINI_AGENTS = "krishna_mini_agents"
    AGENT_MODEL_PROVIDERS = "agent_model_providers"
    AGENT_MODELS = "agent_models"
    #: The models that read images, of the account's connected providers.
    VISION_MODELS = "vision_models"
    #: Models that can draw: what the account's Image Generation setting chooses from.
    IMAGE_GENERATION_MODELS = "image_generation_models"


@dataclass
class FormOptionsContext:
    # The member whose agents fill agent pickers; providers are their account's
    owner: Owner
    provider_settings_repository: ProviderSettingsRepository | None = None
    agent_repository: AgentRepository | None = None
    cache: dict[str, object] = field(default_factory=dict)


#: Sources whose options are complete even when there are none. Other sources can come back empty because a
#: listing failed, so an empty list accepts any value; no configured provider means none can be chosen.
COMPLETE_OPTION_SOURCES = frozenset({FormOptionSourceType.AGENT_MODEL_PROVIDERS})


class FormOptionsResolver(Protocol):
    def resolve(self, context: FormOptionsContext) -> list[SelectOption]:
        ...


def hydrate_form_options(form: Form, context: FormOptionsContext) -> Form:
    """Return a form with hydrate-mode option sources resolved to select options."""
    inputs = []
    for input_def in form.form_inputs:
        source = input_def.options_source
        if not source or source.mode != "hydrate":
            inputs.append(input_def)
            continue

        resolver = FORM_OPTIONS_RESOLVERS.get(source.type)
        if not resolver:
            inputs.append(input_def)
            continue

        inputs.append(input_def.model_copy(update={"options": resolver.resolve(context)}))

    return form.model_copy(update={"form_inputs": inputs})


def validate_form_options(
    form_inputs: list[FormInput],
    values: dict[str, Any],
    context: FormOptionsContext,
) -> None:
    for input_def in form_inputs:
        source = getattr(input_def, "options_source", None)
        if not source:
            continue

        value = values.get(input_def.name)
        if value is None or value == "":
            continue

        resolver = FORM_OPTIONS_RESOLVERS.get(source.type)
        if not resolver:
            continue

        options = resolver.resolve(context)
        if input_def.options_filter:
            options = input_def.options_filter.apply(options, values)
        allowed = {option.value for option in options}
        if (allowed or source.type in COMPLETE_OPTION_SOURCES) and str(value) not in allowed:
            raise ValueError(f"Invalid value for {input_def.name}")


def _owned_agents(context: FormOptionsContext) -> list[Agent]:
    repo = context.agent_repository or AgentRepository()
    return repo.list_owned(context.owner.account_id, context.owner.user_id)


class AgentsOptionsResolver:
    def resolve(self, context: FormOptionsContext) -> list[SelectOption]:
        return [SelectOption(value=agent.agent_id, label=agent.agent_name) for agent in _owned_agents(context)]


class KnowledgeBasesOptionsResolver:
    def resolve(self, context: FormOptionsContext) -> list[SelectOption]:
        from src.knowledge.models import KnowledgeBaseStatus
        from src.knowledge.repository import KnowledgeBaseRepository

        owner = context.owner
        return [
            SelectOption(value=kb.kb_id, label=kb.name)
            for kb in KnowledgeBaseRepository().list_in_account(owner.account_id)
            if kb.owner_id == owner.user_id and kb.status != KnowledgeBaseStatus.DELETED
        ]


class KrishnaMiniAgentsOptionsResolver:
    def resolve(self, context: FormOptionsContext) -> list[SelectOption]:
        return [
            SelectOption(value=agent.agent_id, label=agent.agent_name)
            for agent in _owned_agents(context)
            if agent.agent_architecture == "krishna-mini"
        ]


class AgentModelProvidersOptionsResolver:
    def resolve(self, context: FormOptionsContext) -> list[SelectOption]:
        choices = load_agent_model_choices(context)
        return [SelectOption(value=provider, label=provider) for provider in choices.providers]


class AgentModelsOptionsResolver:
    def resolve(self, context: FormOptionsContext) -> list[SelectOption]:
        return load_agent_model_choices(context).models


class ImageGenerationModelsOptionsResolver:
    def resolve(self, context: FormOptionsContext) -> list[SelectOption]:
        return load_agent_model_choices(context).image_generation_models


class VisionModelsOptionsResolver:
    def resolve(self, context: FormOptionsContext) -> list[SelectOption]:
        return load_agent_model_choices(context).vision_models


@dataclass(frozen=True)
class AgentModelChoices:
    providers: list[str]
    models: list[SelectOption]
    #: The `models` that can read images
    vision_models: list[SelectOption]
    #: The `models` that can draw: what the account's Image Generation setting offers.
    image_generation_models: list[SelectOption] = field(default_factory=list)
    #: Every model listed, with its provider, as the provider described it.
    catalog: list[tuple[str, ModelInfo]] = field(default_factory=list)
    #: Configured providers whose model listing failed this time.
    unlisted: list[str] = field(default_factory=list)


def _configured_providers(context: FormOptionsContext) -> list[tuple[Provider, ProviderSettings]]:
    from src.llm.providers import PROVIDERS

    repo = context.provider_settings_repository or get_provider_settings_repository()
    configured = {settings.provider_name: settings for settings in repo.find_all_in_account(context.owner.account_id)}
    return [(provider, configured[provider.name]) for provider in PROVIDERS if provider.name in configured]


def configured_providers(context: FormOptionsContext) -> list[str]:
    """The providers the account has set up in Settings, in catalog order. Reads the settings only: no provider is
    asked for its models, so it's cheap enough for every turn."""
    return [provider.name for provider, _ in _configured_providers(context)]


def load_agent_model_choices(context: FormOptionsContext) -> AgentModelChoices:
    """The providers set up in Settings and the models each one lists now: what the create-agent form offers and
    `validate_form_options` accepts. Asks every provider, so it's read once per context."""
    cached = context.cache.get("agent_model_choices")
    if isinstance(cached, AgentModelChoices):
        return cached

    # A provider appears once the account has configured it. One whose model listing
    # fails is still offered, so a transient outage doesn't silently drop it from the picker.
    providers: list[str] = []
    catalog: list[tuple[str, ModelInfo]] = []
    unlisted: list[str] = []

    for provider, provider_settings in _configured_providers(context):
        providers.append(provider.name)
        try:
            catalog.extend((provider.name, model) for model in provider.catalog.list_models(provider_settings))
        except Exception as e:
            unlisted.append(provider.name)
            log.warning(
                "Failed to load %s models for account %s: %s",
                provider.name,
                context.owner.account_id,
                e,
            )

    options = [
        (SelectOption(value=model.model_name, label=model.display_name, group=provider), model) for provider, model in catalog
    ]
    choices = AgentModelChoices(
        providers=providers,
        models=[option for option, _ in options],
        vision_models=[
            option for option, model in options if ImageCapability.UNDERSTANDING.value in model.capabilities
        ],
        image_generation_models=[
            option for option, model in options if ImageCapability.GENERATION.value in model.capabilities
        ],
        catalog=catalog,
        unlisted=unlisted,
    )
    context.cache["agent_model_choices"] = choices
    return choices


FORM_OPTIONS_RESOLVERS: dict[str, FormOptionsResolver] = {
    FormOptionSourceType.AGENTS: AgentsOptionsResolver(),
    FormOptionSourceType.KNOWLEDGE_BASES: KnowledgeBasesOptionsResolver(),
    FormOptionSourceType.KRISHNA_MINI_AGENTS: KrishnaMiniAgentsOptionsResolver(),
    FormOptionSourceType.AGENT_MODEL_PROVIDERS: AgentModelProvidersOptionsResolver(),
    FormOptionSourceType.AGENT_MODELS: AgentModelsOptionsResolver(),
    FormOptionSourceType.VISION_MODELS: VisionModelsOptionsResolver(),
    FormOptionSourceType.IMAGE_GENERATION_MODELS: ImageGenerationModelsOptionsResolver(),
}
