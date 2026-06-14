"""Form schemas for smart suggestion settings."""

from __future__ import annotations

from src.form_models import Form, FormInput, FormInputType, FormOptionsSource, SelectOption
from src.form_options import FormOptionSourceType
from src.smart_suggestions.models import SmartSuggestionSettings


def build_smart_suggestion_settings_form(settings: SmartSuggestionSettings | None = None) -> Form:
    enabled_value = "true" if settings and settings.enabled else "false"
    return Form(
        form_name="Smart Suggestions Settings",
        submit_path="/smart-suggestions/settings",
        form_inputs=[
            FormInput(
                input_type=FormInputType.SELECT,
                name="enabled",
                label="Smart suggestions",
                value=enabled_value,
                options=[
                    SelectOption(value="true", label="Enabled"),
                    SelectOption(value="false", label="Disabled"),
                ],
            ),
            FormInput(
                input_type=FormInputType.SELECT,
                name="provider_name",
                label="Provider",
                value=settings.provider_name if settings else None,
                options_source=FormOptionsSource(type=FormOptionSourceType.AGENT_MODEL_PROVIDERS),
            ),
            FormInput(
                input_type=FormInputType.SELECT,
                name="model_name",
                label="Model",
                value=settings.model_name if settings else None,
                options_source=FormOptionsSource(type=FormOptionSourceType.AGENT_MODELS),
            ),
        ],
    )

