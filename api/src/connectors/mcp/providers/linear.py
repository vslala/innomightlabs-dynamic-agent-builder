from __future__ import annotations

from src.connectors.mcp.delivery import BearerHeader
from src.connectors.mcp.providers.base import DiscoveredOAuth, MCPProvider
from src.connectors.mcp.resolved import HttpTarget

LINEAR_MCP_URL = "https://mcp.linear.app/mcp"

PROVIDER = MCPProvider(
    key="linear",
    display_name="Linear",
    description="Find and update issues, projects and cycles in Linear.",
    icon="linear",
    category="productivity",
    tags=("issues", "tickets", "sprint", "project management", "bugs"),
    docs_url="https://linear.app/docs/mcp",
    target=lambda install: HttpTarget(LINEAR_MCP_URL),
    oauth=DiscoveredOAuth(server_url=LINEAR_MCP_URL, delivery=BearerHeader()),
)
