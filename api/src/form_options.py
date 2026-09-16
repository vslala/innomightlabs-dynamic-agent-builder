from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.agents.repository import AgentRepository
from src.form_models import Form, FormInput, SelectOption
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository

log = logging.getLogger(__name__)


class FormOptionSourceType:
    AGENTS = "agents"
    KRISHNA_MINI_AGENTS = "krishna_mini_agents"
    AGENT_MODEL_PROVIDERS = "agent_model_providers"
    AGENT_MODELS = "agent_models"


@dataclass
class FormOptionsContext:
    user_email: str
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

        allowed = {option.value for option in resolver.resolve(context)}
        if allowed and str(value) not in allowed:
            raise ValueError(f"Invalid value for {input_def.name}")


class AgentsOptionsResolver:
    def resolve(self, context: FormOptionsContext) -> list[SelectOption]:
        repo = context.agent_repository or AgentRepository()
        return [
            SelectOption(value=agent.agent_id, label=agent.agent_name)
            for agent in repo.find_all_by_created_by(context.user_email)
        ]


class KrishnaMiniAgentsOptionsResolver:
    def resolve(self, context: FormOptionsContext) -> list[SelectOption]:
        repo = context.agent_repository or AgentRepository()
        return [
            SelectOption(value=agent.agent_id, label=agent.agent_name)
            for agent in repo.find_all_by_created_by(context.user_email)
            if agent.agent_architecture == "krishna-mini"
        ]


class AgentModelProvidersOptionsResolver:
    def resolve(self, context: FormOptionsContext) -> list[SelectOption]:
        choices = _load_agent_model_choices(context)
        return [SelectOption(value=provider, label=provider) for provider in choices.providers]


class AgentModelsOptionsResolver:
    def resolve(self, context: FormOptionsContext) -> list[SelectOption]:
        return _load_agent_model_choices(context).models


@dataclass(frozen=True)
class AgentModelChoices:
    providers: list[str]
    models: list[SelectOption]


def _load_agent_model_choices(context: FormOptionsContext) -> AgentModelChoices:
    from src.llm.models import PROVIDER_MODEL_SOURCES, models_service

    cached = context.cache.get("agent_model_choices")
    if isinstance(cached, AgentModelChoices):
        return cached

    repo = context.provider_settings_repository or get_provider_settings_repository()

    # Bedrock is always offered; every other provider appears once the user has
    # configured it. A provider whose model listing fails is still offered, so a
    # transient outage doesn't silently drop it from the picker.
    providers = ["Bedrock"]
    model_options = [
        SelectOption(value=model.model_name, label=model.display_name)
        for model in models_service.get_bedrock_models()
    ]

    for source in PROVIDER_MODEL_SOURCES:
        provider_settings = repo.find_by_provider(
            user_email=context.user_email,
            provider_name=source.provider_name,
        )
        if not provider_settings:
            continue

        providers.append(source.provider_name)
        try:
            model_options.extend(
                SelectOption(value=model.model_name, label=model.display_name)
                for model in source.load_models(provider_settings)
            )
        except Exception as e:
            log.warning(
                "Failed to load %s models for user %s: %s",
                source.provider_name,
                context.user_email,
                e,
            )

    choices = AgentModelChoices(providers=providers, models=model_options)
    context.cache["agent_model_choices"] = choices
    return choices


FORM_OPTIONS_RESOLVERS: dict[str, FormOptionsResolver] = {
    FormOptionSourceType.AGENTS: AgentsOptionsResolver(),
    FormOptionSourceType.KRISHNA_MINI_AGENTS: KrishnaMiniAgentsOptionsResolver(),
    FormOptionSourceType.AGENT_MODEL_PROVIDERS: AgentModelProvidersOptionsResolver(),
    FormOptionSourceType.AGENT_MODELS: AgentModelsOptionsResolver(),
}
