from __future__ import annotations

from src.connectors.mcp.delivery import BearerHeader
from src.connectors.mcp.models import MCPOAuthProviderConfig
from src.connectors.mcp.providers.base import FixedOAuth, MCPProvider, ProviderInstall, oauth_client_inputs
from src.connectors.mcp.resolved import HttpTarget
from src.form_models import FormInput, FormInputType, SelectOption

GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/"
GITHUB_TOOLSETS = ("repos", "issues", "pull_requests", "actions", "code_security")


def _target(install: ProviderInstall) -> HttpTarget:
    headers = {
        # OAuth App scopes are coarse (`repo` includes write), so read-only is enforced here unless the user
        # opts in: agents act unattended, and writes need an explicit choice.
        "X-MCP-Readonly": "false" if install.inputs.get("allow_writes") == "yes" else "true",
    }
    toolsets = ",".join(item.strip() for item in install.inputs.get("toolsets", "").split(",") if item.strip())
    if toolsets:
        headers["X-MCP-Toolsets"] = toolsets
    return HttpTarget(GITHUB_MCP_URL, headers)


def _oauth_config(install: ProviderInstall) -> MCPOAuthProviderConfig:
    return MCPOAuthProviderConfig.model_validate(
        {
            "authorization_url": "https://github.com/login/oauth/authorize",
            "token_url": "https://github.com/login/oauth/access_token",
            "client_id": install.oauth_client_id,
            "client_secret": install.oauth_client_secret,
            "scope": "repo read:org read:user",
        }
    )


PROVIDER = MCPProvider(
    key="github",
    display_name="GitHub",
    description="Repositories, issues, pull requests, and Actions.",
    icon="github",
    docs_url="https://github.com/github/github-mcp-server",
    inputs=(
        *oauth_client_inputs("GitHub → Settings → Developer settings → OAuth Apps"),
        FormInput(
            input_type=FormInputType.TEXT,
            name="toolsets",
            label="Toolsets",
            attr={
                "optional": "true",
                "placeholder": ",".join(GITHUB_TOOLSETS),
                "help_text": "Comma-separated. Leave blank for GitHub's default toolsets.",
            },
        ),
        FormInput(
            input_type=FormInputType.SELECT,
            name="allow_writes",
            label="Allow write actions",
            value="no",
            options=[
                SelectOption(value="no", label="No (read-only)"),
                SelectOption(value="yes", label="Yes"),
            ],
            attr={"optional": "true"},
        ),
    ),
    target=_target,
    # GitHub OAuth App tokens don't expire and come without a refresh token (see MCPOAuthCredentials.expires_at).
    oauth=FixedOAuth(config=_oauth_config, delivery=BearerHeader()),
)
