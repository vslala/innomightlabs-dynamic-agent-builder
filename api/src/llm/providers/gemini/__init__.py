"""Google Gemini, with an API key: chat, and drawing with its image models."""

from google.genai import errors as genai_errors

from src.form_models import Form, FormInput, FormInputType
from src.llm.providers.provider import Provider

from .catalog import GeminiCatalog
from .chat import GeminiProvider
from .images import GeminiImages

GEMINI = Provider(
    name="Gemini",
    title="Gemini",
    settings_form=Form(
        form_name="Google Gemini Configuration",
        submit_path="/settings/providers/Gemini",
        form_inputs=[FormInput(input_type=FormInputType.PASSWORD, name="api_key", label="Gemini API Key")],
    ),
    chat=GeminiProvider(),
    catalog=GeminiCatalog(),
    refuses_model=lambda exc: isinstance(exc, genai_errors.ClientError) and exc.code == 404,
    images=GeminiImages(),
)
