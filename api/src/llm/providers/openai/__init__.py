"""OpenAI through a ChatGPT sign-in: the Codex backend, reached with the admin's OAuth token."""

from src.config import settings
from src.form_models import Form, FormInput, FormInputType
from src.llm.providers.provider import OAuthSignIn, Provider
from src.llm.wire.responses import responses_refuses_model
from src.llm.wire.responses_images import ResponsesToolImages

from .catalog import OpenAICatalog
from .chat import OpenAIProvider
from .credentials import OpenAISignInCredentials

OPENAI = Provider(
    name="OpenAI",
    title="OpenAI (OAuth)",
    settings_form=Form(
        form_name="OpenAI OAuth Configuration",
        submit_path="/auth/openai/complete",
        form_inputs=[
            FormInput(
                input_type=FormInputType.TEXT,
                name="callback_url",
                label="Paste callback URL",
                attr={"type": "url", "placeholder": "http://localhost:1455/auth/callback?code=...&state=..."},
            )
        ],
    ),
    chat=OpenAIProvider(),
    catalog=OpenAICatalog(),
    oauth=OAuthSignIn(
        start_path="/auth/openai/start",
        button_label="Open OpenAI Login",
        guide=(
            "1. Click Open OpenAI Login. 2. Sign in and approve access. 3. Copy the full localhost callback URL from "
            "your browser (the page may fail to load). 4. Paste that URL below and submit."
        ),
    ),
    credentials=OpenAISignInCredentials(),
    refuses_model=responses_refuses_model,
    images=ResponsesToolImages(
        url=settings.openai_oauth_responses_url,
        credential_field="access_token",
        label="OpenAI Codex",
        provider_key="openai_codex",
    ),
)
