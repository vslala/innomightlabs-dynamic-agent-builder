"""Schema-driven configuration form for Dream settings."""

from src.dream.models import DreamSettings
from src.form_models import (
    Form,
    FormInput,
    FormInputType,
    FormOptionsSource,
    SelectOption,
    SmartSuggestionConfig,
)
from src.smart_suggestions.models import SmartSuggestionType
from src.form_options import FormOptionSourceType


def build_dream_settings_form(settings: DreamSettings | None = None) -> Form:
    return Form(
        form_name="Dream Settings",
        submit_path="/dream/settings",
        form_inputs=[
            FormInput(input_type=FormInputType.SELECT, name="enabled", label="Nightly dreaming", value="true" if settings and settings.enabled else "false", options=[SelectOption(value="true", label="Enabled"), SelectOption(value="false", label="Disabled")]),
            FormInput(input_type=FormInputType.SELECT, name="provider_name", label="Provider", value=settings.provider_name if settings else None, options_source=FormOptionsSource(type=FormOptionSourceType.AGENT_MODEL_PROVIDERS)),
            FormInput(input_type=FormInputType.SEARCH, name="model_name", label="Model", value=settings.model_name if settings else None, options_source=FormOptionsSource(type=FormOptionSourceType.AGENT_MODELS)),
            FormInput(
                input_type=FormInputType.TEXT,
                name="cron_expression",
                label="Cron expression",
                value=settings.cron_expression if settings else "0 3 * * *",
                attr={"placeholder": "0 3 * * *"},
                smart_suggestion=SmartSuggestionConfig(
                    suggestion_type=SmartSuggestionType.CRON_EXPRESSION,
                    button_label="Build schedule",
                    prompt_placeholder="e.g. Every weekday at 9:30 AM in my timezone",
                ),
            ),
            FormInput(input_type=FormInputType.TEXT, name="timezone", label="Timezone", value=settings.timezone if settings else "UTC"),
        ],
    )
