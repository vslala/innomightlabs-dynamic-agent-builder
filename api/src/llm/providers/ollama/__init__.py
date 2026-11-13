"""A user-hosted Ollama server, reached at the endpoint the account configures."""

from src.form_models import Form, FormInput, FormInputType
from src.llm.providers.provider import Provider

from .catalog import OllamaCatalog
from .chat import OllamaProvider
from .connection import merge_thinking_override

OLLAMA = Provider(
    name="Ollama",
    title="Ollama",
    settings_form=Form(
        form_name="Ollama Configuration",
        submit_path="/settings/providers/Ollama",
        form_inputs=[
            FormInput(
                input_type=FormInputType.TEXT,
                name="endpoint_url",
                label="Endpoint URL",
                attr={
                    "type": "url",
                    "placeholder": "http://localhost:11434",
                    "help_text": "Base URL of your Ollama server. Models are listed from this endpoint.",
                },
            ),
            FormInput(
                input_type=FormInputType.PASSWORD,
                name="api_key",
                label="API Key (optional)",
                attr={
                    "optional": "true",
                    "help_text": (
                        "Only needed when the endpoint sits behind a proxy or gateway "
                        "requiring a bearer token. Leave blank for a plain local Ollama."
                    ),
                },
            ),
        ],
    ),
    chat=OllamaProvider(),
    catalog=OllamaCatalog(),
    refuses_model=lambda exc: "does not have model" in str(exc),
    apply_thinking=merge_thinking_override,
)
