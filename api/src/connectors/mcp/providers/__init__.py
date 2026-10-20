from __future__ import annotations

from src.connectors.mcp.providers import (
    atlassian,
    canva,
    context7,
    github,
    google_ads,
    hubspot,
    linear,
    notion,
    sentry,
    slack,
    stripe,
    supabase,
    tavily,
)
from src.connectors.mcp.providers.base import MCPProvider

PROVIDERS: dict[str, MCPProvider] = {
    provider.key: provider
    for provider in (
        google_ads.PROVIDER,
        atlassian.PROVIDER,
        github.PROVIDER,
        canva.PROVIDER,
        tavily.PROVIDER,
        notion.PROVIDER,
        linear.PROVIDER,
        sentry.PROVIDER,
        supabase.PROVIDER,
        context7.PROVIDER,
        slack.PROVIDER,
        stripe.PROVIDER,
        hubspot.PROVIDER,
    )
}


def get_provider(key: str | None) -> MCPProvider:
    provider = PROVIDERS.get(key or "")
    if provider is None:
        raise ValueError(f"MCP provider not found: {key}")
    return provider
