from __future__ import annotations

from src.connectors.mcp.providers.base import MCPProvider, ProviderInstall
from src.connectors.mcp.resolved import HttpTarget
from src.form_models import FormInput, FormInputType

EXA_MCP_URL = "https://mcp.exa.ai/mcp"


def _target(install: ProviderInstall) -> HttpTarget:
    api_key = install.inputs.get("api_key")
    return HttpTarget(EXA_MCP_URL, {"x-api-key": api_key} if api_key else {})


PROVIDER = MCPProvider(
    key="exa",
    display_name="Exa",
    description="Search the web and fetch page content, with free rate-limited keyless access.",
    icon="exa",
    category="search",
    tags=("web", "search", "research", "fetch"),
    docs_url="https://docs.exa.ai/reference/exa-mcp",
    inputs=(
        FormInput(
            input_type=FormInputType.PASSWORD,
            name="api_key",
            label="API key",
            attr={"optional": "true", "help_text": "Optional. Without a key Exa applies free rate limits. With a key, usage uses your Exa plan."},
        ),
    ),
    target=_target,
)
