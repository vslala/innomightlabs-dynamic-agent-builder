"""
Form schemas for provider configurations.

Each supported LLM provider has a form schema defining the required credentials.
"""

from src.form_models import Form, FormInput, FormInputType


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
}

# List of all supported provider names
SUPPORTED_PROVIDERS = list(PROVIDER_SCHEMAS.keys())


def get_provider_schema(provider_name: str) -> Form | None:
    """
    Get the form schema for a provider.

    Args:
        provider_name: Name of the provider (e.g., "Bedrock")

    Returns:
        Form schema if provider is supported, None otherwise
    """
    return PROVIDER_SCHEMAS.get(provider_name)


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
