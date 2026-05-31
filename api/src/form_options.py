from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.agents.repository import AgentRepository
from src.form_models import Form, FormInput, SelectOption
from src.llm.models import models_service
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository

log = logging.getLogger(__name__)


class FormOptionSourceType:
    AGENTS = "agents"
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
    cached = context.cache.get("agent_model_choices")
    if isinstance(cached, AgentModelChoices):
        return cached

    repo = context.provider_settings_repository or get_provider_settings_repository()
    bedrock_models = models_service.get_bedrock_models()
    providers = ["Bedrock"]
    model_options = [
        SelectOption(value=model.model_name, label=model.display_name)
        for model in bedrock_models
    ]

    anthropic_settings = repo.find_by_provider(
        user_email=context.user_email,
        provider_name="Anthropic",
    )
    if anthropic_settings:
        try:
            anthropic_models = models_service.get_anthropic_models(
                provider_settings=anthropic_settings
            )
            providers.append("Anthropic")
            model_options.extend(
                SelectOption(value=model.model_name, label=model.display_name)
                for model in anthropic_models
            )
        except Exception as e:
            log.warning("Failed to load Anthropic models for user %s: %s", context.user_email, e)

    openai_settings = repo.find_by_provider(
        user_email=context.user_email,
        provider_name="OpenAI",
    )
    if openai_settings:
        providers.append("OpenAI")
        try:
            openai_models = models_service.get_openai_models()
            model_options.extend(
                SelectOption(value=model.model_name, label=model.display_name)
                for model in openai_models
            )
        except Exception as e:
            log.warning("Failed to load OpenAI models for user %s: %s", context.user_email, e)

    choices = AgentModelChoices(providers=providers, models=model_options)
    context.cache["agent_model_choices"] = choices
    return choices


FORM_OPTIONS_RESOLVERS: dict[str, FormOptionsResolver] = {
    FormOptionSourceType.AGENTS: AgentsOptionsResolver(),
    FormOptionSourceType.AGENT_MODEL_PROVIDERS: AgentModelProvidersOptionsResolver(),
    FormOptionSourceType.AGENT_MODELS: AgentModelsOptionsResolver(),
}
