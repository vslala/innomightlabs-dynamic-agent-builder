from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.accounts.owner import Owner
from src.agents.image_generation.capabilities import ImageCapability
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.form_models import Form, FormInput, SelectOption
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository

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


@dataclass
class FormOptionsContext:
    # The member whose agents fill agent pickers; providers are their account's
    owner: Owner
    provider_settings_repository: ProviderSettingsRepository | None = None
    agent_repository: AgentRepository | None = None
    cache: dict[str, object] = field(default_factory=dict)


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
        if allowed and str(value) not in allowed:
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
        choices = _load_agent_model_choices(context)
        return [SelectOption(value=provider, label=provider) for provider in choices.providers]


class AgentModelsOptionsResolver:
    def resolve(self, context: FormOptionsContext) -> list[SelectOption]:
        return _load_agent_model_choices(context).models


class VisionModelsOptionsResolver:
    def resolve(self, context: FormOptionsContext) -> list[SelectOption]:
        return _load_agent_model_choices(context).vision_models


@dataclass(frozen=True)
class AgentModelChoices:
    providers: list[str]
    models: list[SelectOption]
    #: The `models` that can read images
    vision_models: list[SelectOption]


def _load_agent_model_choices(context: FormOptionsContext) -> AgentModelChoices:
    from src.llm.models import PROVIDER_MODEL_SOURCES, models_service

    cached = context.cache.get("agent_model_choices")
    if isinstance(cached, AgentModelChoices):
        return cached

    repo = context.provider_settings_repository or get_provider_settings_repository()

    # Bedrock is always offered; every other provider appears once the account has
    # configured it. A provider whose model listing fails is still offered, so a
    # transient outage doesn't silently drop it from the picker.
    providers = ["Bedrock"]
    catalog = [("Bedrock", model) for model in models_service.get_bedrock_models()]

    for source in PROVIDER_MODEL_SOURCES:
        provider_settings = repo.find_by_provider(context.owner.account_id, source.provider_name)
        if not provider_settings:
            continue

        providers.append(source.provider_name)
        try:
            catalog.extend((source.provider_name, model) for model in source.load_models(provider_settings))
        except Exception as e:
            log.warning(
                "Failed to load %s models for account %s: %s",
                source.provider_name,
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
}
