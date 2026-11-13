"""Claude through the Anthropic API, with an API key."""

import anthropic

from src.form_models import Form, FormInput, FormInputType
from src.llm.providers.provider import Provider

from .catalog import AnthropicCatalog
from .chat import AnthropicProvider

ANTHROPIC = Provider(
    name="Anthropic",
    title="Anthropic",
    settings_form=Form(
        form_name="Anthropic Configuration",
        submit_path="/settings/providers/Anthropic",
        form_inputs=[FormInput(input_type=FormInputType.PASSWORD, name="api_key", label="Anthropic API Key")],
    ),
    chat=AnthropicProvider(),
    catalog=AnthropicCatalog(),
    refuses_model=lambda exc: isinstance(exc, anthropic.NotFoundError),
)
