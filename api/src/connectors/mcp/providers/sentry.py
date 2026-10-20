from __future__ import annotations

from src.connectors.mcp.delivery import BearerHeader
from src.connectors.mcp.providers.base import DiscoveredOAuth, MCPProvider
from src.connectors.mcp.resolved import HttpTarget

SENTRY_MCP_URL = "https://mcp.sentry.dev/mcp"

PROVIDER = MCPProvider(
    key="sentry",
    display_name="Sentry",
    description="Investigate errors, issues and performance in Sentry.",
    icon="sentry",
    category="development",
    tags=("errors", "exceptions", "monitoring", "crashes", "debugging"),
    docs_url="https://mcp.sentry.dev/",
    target=lambda install: HttpTarget(SENTRY_MCP_URL),
    oauth=DiscoveredOAuth(server_url=SENTRY_MCP_URL, delivery=BearerHeader()),
)
