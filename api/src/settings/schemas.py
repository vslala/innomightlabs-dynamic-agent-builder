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

# Map of provider name -> form schema
PROVIDER_SCHEMAS: dict[str, Form] = {
    "Bedrock": BEDROCK_PROVIDER_FORM,
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
