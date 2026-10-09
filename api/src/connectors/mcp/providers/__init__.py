from __future__ import annotations

from src.connectors.mcp.providers import atlassian, canva, github, google_ads, tavily
from src.connectors.mcp.providers.base import MCPProvider

PROVIDERS: dict[str, MCPProvider] = {
    provider.key: provider
    for provider in (google_ads.PROVIDER, atlassian.PROVIDER, github.PROVIDER, canva.PROVIDER, tavily.PROVIDER)
}


def get_provider(key: str | None) -> MCPProvider:
    provider = PROVIDERS.get(key or "")
    if provider is None:
        raise ValueError(f"MCP provider not found: {key}")
    return provider
