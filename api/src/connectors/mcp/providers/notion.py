from __future__ import annotations

from src.connectors.mcp.delivery import BearerHeader
from src.connectors.mcp.providers.base import DiscoveredOAuth, MCPProvider
from src.connectors.mcp.resolved import HttpTarget

NOTION_MCP_URL = "https://mcp.notion.com/mcp"

PROVIDER = MCPProvider(
    key="notion",
    display_name="Notion",
    description="Search, read and write pages, docs and databases in Notion.",
    icon="notion",
    category="productivity",
    featured=True,
    tags=("notes", "wiki", "docs", "database", "tasks"),
    docs_url="https://developers.notion.com/guides/mcp/get-started-with-mcp",
    target=lambda install: HttpTarget(NOTION_MCP_URL),
    oauth=DiscoveredOAuth(server_url=NOTION_MCP_URL, delivery=BearerHeader()),
)
