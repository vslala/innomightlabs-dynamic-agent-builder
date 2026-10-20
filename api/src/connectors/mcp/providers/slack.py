from __future__ import annotations

from src.connectors.mcp.delivery import BearerHeader
from src.connectors.mcp.models import MCPOAuthProviderConfig
from src.connectors.mcp.providers.base import FixedOAuth, MCPProvider, ProviderInstall, oauth_client_inputs
from src.connectors.mcp.resolved import HttpTarget
from src.form_models import FormInput, FormInputType, SelectOption

SLACK_MCP_URL = "https://mcp.slack.com/mcp"

# User-token scopes from the server's resource metadata, split so agents that run unattended read by default.
READ_SCOPES = (
    "channels:history",
    "channels:read",
    "groups:history",
    "groups:read",
    "im:history",
    "im:read",
    "mpim:history",
    "mpim:read",
    "search:read.public",
    "search:read.private",
    "search:read.im",
    "search:read.mpim",
    "search:read.files",
    "search:read.users",
    "users:read",
    "users:read.email",
    "files:read",
    "canvases:read",
    "lists:read",
    "reactions:read",
    "emoji:read",
)
WRITE_SCOPES = ("chat:write", "reactions:write", "canvases:write", "lists:write", "files:write")


def _oauth_config(install: ProviderInstall) -> MCPOAuthProviderConfig:
    scopes = READ_SCOPES + (WRITE_SCOPES if install.inputs.get("allow_writes") == "yes" else ())
    return MCPOAuthProviderConfig.model_validate(
        {
            "authorization_url": "https://slack.com/oauth/v2_user/authorize",
            "token_url": "https://slack.com/api/oauth.v2.user.access",
            "client_id": install.oauth_client_id,
            "client_secret": install.oauth_client_secret,
            "scope": " ".join(scopes),
            "resource_url": SLACK_MCP_URL,
        }
    )


PROVIDER = MCPProvider(
    key="slack",
    display_name="Slack",
    description="Search and read channels and messages in Slack.",
    icon="slack",
    category="productivity",
    featured=True,
    tags=("chat", "messages", "channels", "team", "dm"),
    docs_url="https://docs.slack.dev/ai/slack-mcp-server/",
    # Slack only lets MCP clients backed by a registered (internal or Marketplace) app sign in, so the user brings one.
    inputs=(
        *oauth_client_inputs("your Slack app (api.slack.com/apps); a workspace admin must approve MCP access"),
        FormInput(
            input_type=FormInputType.SELECT,
            name="allow_writes",
            label="Allow posting and edits",
            value="no",
            options=[
                SelectOption(value="no", label="No (read-only)"),
                SelectOption(value="yes", label="Yes"),
            ],
            attr={"optional": "true"},
        ),
    ),
    target=lambda install: HttpTarget(SLACK_MCP_URL),
    oauth=FixedOAuth(config=_oauth_config, delivery=BearerHeader()),
)
