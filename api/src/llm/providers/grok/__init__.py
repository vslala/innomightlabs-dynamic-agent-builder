"""xAI's Grok, with the account's xAI API key: chat through its Responses API, drawing with its image models."""

from src.form_models import Form, FormInput, FormInputType
from src.llm.providers.provider import Provider
from src.llm.wire.responses import responses_refuses_model

from .catalog import GrokCatalog
from .chat import GrokProvider
from .images import GrokImages

GROK = Provider(
    name="Grok",
    title="Grok (xAI)",
    settings_form=Form(
        form_name="Grok (xAI) API Key Configuration",
        submit_path="/settings/providers/Grok",
        form_inputs=[
            FormInput(
                input_type=FormInputType.PASSWORD,
                name="api_key",
                label="xAI API Key",
                attr={
                    "placeholder": "xai-...",
                    "help_text": "A key from console.x.ai. Usage is billed to that xAI team.",
                },
            )
        ],
    ),
    chat=GrokProvider(),
    catalog=GrokCatalog(),
    refuses_model=responses_refuses_model,
    images=GrokImages(),
)
