from __future__ import annotations

from src.connectors.mcp.providers import atlassian, canva, github
from src.connectors.mcp.providers.base import MCPProvider

PROVIDERS: dict[str, MCPProvider] = {
    provider.key: provider
    for provider in (atlassian.PROVIDER, github.PROVIDER, canva.PROVIDER)
}


def get_provider(key: str | None) -> MCPProvider:
    provider = PROVIDERS.get(key or "")
    if provider is None:
        raise ValueError(f"MCP provider not found: {key}")
    return provider
