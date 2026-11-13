"""OpenAI through the public API, with the account's own API key."""

from src.form_models import Form, FormInput, FormInputType
from src.llm.providers.openai.chat import responses_refuses_model
from src.llm.providers.provider import Provider

from .catalog import OpenAIAPICatalog
from .chat import OpenAIAPIProvider

OPENAI_API = Provider(
    name="OpenAIAPI",
    title="OpenAI (API key)",
    settings_form=Form(
        form_name="OpenAI API Key Configuration",
        submit_path="/settings/providers/OpenAIAPI",
        form_inputs=[
            FormInput(
                input_type=FormInputType.PASSWORD,
                name="api_key",
                label="OpenAI API Key",
                attr={
                    "placeholder": "sk-...",
                    "help_text": "A project or service-account key from platform.openai.com. Usage is billed to that account.",
                },
            )
        ],
    ),
    chat=OpenAIAPIProvider(),
    catalog=OpenAIAPICatalog(),
    refuses_model=responses_refuses_model,
)
