"""
Form schemas for provider configurations.

Each supported LLM provider has a form schema defining the required credentials.
"""

from src.form_models import Form, FormInput, FormInputType
from src.config import settings


ANTHROPIC_OAUTH_PROVIDER = "AnthropicOAuth"


# Bedrock provider configuration form
BEDROCK_PROVIDER_FORM = Form(
    form_name="AWS Bedrock Configuration",
    submit_path="/settings/providers/Bedrock",
    form_inputs=[
        FormInput(
            input_type=FormInputType.PASSWORD,
            name="access_key",
            label="AWS Access Key",
        ),
        FormInput(
            input_type=FormInputType.PASSWORD,
            name="secret_key",
            label="AWS Secret Key",
        ),
    ],
)

ANTHROPIC_PROVIDER_FORM = Form(
    form_name="Anthropic Configuration",
    submit_path="/settings/providers/Anthropic",
    form_inputs=[
        FormInput(
            input_type=FormInputType.PASSWORD,
            name="api_key",
            label="Anthropic API Key"
        )
    ]
)

ANTHROPIC_OAUTH_PROVIDER_FORM = Form(
    form_name="Anthropic OAuth Configuration",
    submit_path=f"/settings/providers/{ANTHROPIC_OAUTH_PROVIDER}",
    form_inputs=[
        FormInput(
            input_type=FormInputType.PASSWORD,
            name="refresh_token",
            label="Anthropic OAuth Refresh Token",
        ),
        FormInput(
            input_type=FormInputType.TEXT,
            name="client_id",
            label="Anthropic OAuth Client ID",
        ),
    ],
)

GEMINI_PROVIDER_FORM = Form(
    form_name="Google Gemini Configuration",
    submit_path="/settings/providers/Gemini",
    form_inputs=[
        FormInput(
            input_type=FormInputType.PASSWORD,
            name="api_key",
            label="Gemini API Key"
        )
    ]
)

OPENAI_PROVIDER_FORM = Form(
    form_name="OpenAI OAuth Configuration",
    submit_path="/auth/openai/complete",
    form_inputs=[
        FormInput(
            input_type=FormInputType.TEXT,
            name="callback_url",
            label="Paste callback URL",
            attr={
                "type": "url",
                "placeholder": "http://localhost:1455/auth/callback?code=...&state=...",
            },
        )
    ],
)

# Map of provider name -> form schema
PROVIDER_SCHEMAS: dict[str, Form] = {
    "Bedrock": BEDROCK_PROVIDER_FORM,
    "Anthropic": ANTHROPIC_PROVIDER_FORM,
    "OpenAI": OPENAI_PROVIDER_FORM,
    "Gemini": GEMINI_PROVIDER_FORM,
}

def get_supported_provider_schemas() -> dict[str, Form]:
    """Return provider schemas available in the current feature-flag configuration."""
    schemas = PROVIDER_SCHEMAS.copy()
    if settings.anthropic_oauth_shortcircuit_enabled:
        schemas[ANTHROPIC_OAUTH_PROVIDER] = ANTHROPIC_OAUTH_PROVIDER_FORM
    return schemas


def get_supported_providers() -> list[str]:
    """Return provider names available in the current feature-flag configuration."""
    return list(get_supported_provider_schemas().keys())


def get_provider_schema(provider_name: str) -> Form | None:
    """
    Get the form schema for a provider.

    Args:
        provider_name: Name of the provider (e.g., "Bedrock")

    Returns:
        Form schema if provider is supported, None otherwise
    """
    return get_supported_provider_schemas().get(provider_name)


def get_agent2agent_settings_schema() -> Form:
    return Form(
        form_name="Agent2Agent Trust Settings",
        submit_path="/settings/agent2agent",
        form_inputs=[
            FormInput(
                input_type=FormInputType.KEY_VALUE,
                name="allowed_origins",
                label="Allowed Agent2Agent Origins",
                attr={
                    "key_placeholder": "https://api.example.com or http://localhost:1455",
                    "value_placeholder": "Optional label",
                    "add_label": "Add origin",
                    "empty_text": "No Agent2Agent origins are allowlisted.",
                },
            )
        ],
    )
