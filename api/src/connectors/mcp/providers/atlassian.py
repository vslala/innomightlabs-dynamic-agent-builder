from __future__ import annotations

from src.connectors.mcp.delivery import BearerHeader
from src.connectors.mcp.providers.base import DiscoveredOAuth, MCPProvider
from src.connectors.mcp.resolved import HttpTarget

ATLASSIAN_MCP_URL = "https://mcp.atlassian.com/v2/mcp"

PROVIDER = MCPProvider(
    key="atlassian",
    display_name="Atlassian",
    description="Search and update Jira, Confluence, and Compass.",
    icon="atlassian",
    docs_url="https://support.atlassian.com/atlassian-rovo-mcp-server/",
    target=lambda install: HttpTarget(ATLASSIAN_MCP_URL),
    oauth=DiscoveredOAuth(server_url=ATLASSIAN_MCP_URL, delivery=BearerHeader()),
)
