from __future__ import annotations

from src.connectors.mcp.delivery import GoogleAuthorizedUserFile
from src.connectors.mcp.models import MCPOAuthProviderConfig, MCPTransport
from src.connectors.mcp.providers.base import FixedOAuth, MCPProvider, ProviderInstall, oauth_client_inputs
from src.connectors.mcp.resolved import StdioTarget
from src.form_models import FormInput, FormInputType

# Optional inputs mapped to the env vars google-ads-mcp reads (ads_mcp/utils.py at the pinned commit).
OPTIONAL_ENV = {
    "login_customer_id": "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
    # Not read by the pinned server code; passed through because the provider's docs list it.
    "project_id": "GOOGLE_PROJECT_ID",
}


def _target(install: ProviderInstall) -> StdioTarget:
    # No developer token: Google sunset them on 2026-09-09. API access now follows the Google Cloud project that owns
    # the OAuth client, and the server only sends a token when one is set.
    env: dict[str, str] = {}
    for input_name, env_name in OPTIONAL_ENV.items():
        if install.inputs.get(input_name):
            env[env_name] = install.inputs[input_name]
    return StdioTarget(package="google_ads", env=env)


def _oauth_config(install: ProviderInstall) -> MCPOAuthProviderConfig:
    return MCPOAuthProviderConfig.model_validate(
        {
            "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "client_id": install.oauth_client_id,
            "client_secret": install.oauth_client_secret,
            "scope": "https://www.googleapis.com/auth/adwords",
            # Google returns a refresh token only for offline access, and only on a fresh consent.
            "authorization_params": {"access_type": "offline", "prompt": "consent"},
        }
    )


PROVIDER = MCPProvider(
    key="google_ads",
    display_name="Google Ads",
    description="Query campaigns, performance, and account structure with GAQL.",
    icon="google_ads",
    docs_url="https://github.com/googleads/google-ads-mcp",
    transport=MCPTransport.STDIO,
    inputs=(
        *oauth_client_inputs("your Google Cloud project (Web application type, Google Ads API enabled)"),
        FormInput(
            input_type=FormInputType.TEXT,
            name="login_customer_id",
            label="Manager account ID",
            attr={
                "optional": "true",
                "placeholder": "1234567890",
                "help_text": "Only needed when you access accounts through a manager account.",
            },
        ),
        FormInput(
            input_type=FormInputType.TEXT,
            name="project_id",
            label="Google Cloud project ID",
            attr={"optional": "true"},
        ),
    ),
    target=_target,
    # google-auth refreshes access tokens itself from the authorized_user file, so the server never restarts on refresh.
    oauth=FixedOAuth(config=_oauth_config, delivery=GoogleAuthorizedUserFile()),
)
