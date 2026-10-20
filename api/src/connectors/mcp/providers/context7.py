from __future__ import annotations

from src.connectors.mcp.providers.base import MCPProvider, ProviderInstall
from src.connectors.mcp.resolved import HttpTarget
from src.form_models import FormInput, FormInputType

CONTEXT7_MCP_URL = "https://mcp.context7.com/mcp"


def _target(install: ProviderInstall) -> HttpTarget:
    api_key = install.inputs.get("api_key")
    return HttpTarget(CONTEXT7_MCP_URL, {"Authorization": f"Bearer {api_key}"} if api_key else {})


PROVIDER = MCPProvider(
    key="context7",
    display_name="Context7",
    description="Up-to-date library and framework documentation for coding questions.",
    icon="context7",
    category="development",
    featured=True,
    tags=("docs", "documentation", "libraries", "api reference", "coding"),
    docs_url="https://context7.com/docs",
    inputs=(
        FormInput(
            input_type=FormInputType.PASSWORD,
            name="api_key",
            label="API key",
            attr={"optional": "true", "help_text": "Optional. Without a key Context7 applies lower rate limits."},
        ),
    ),
    target=_target,
)
