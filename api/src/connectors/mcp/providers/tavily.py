from __future__ import annotations

from src.connectors.mcp.delivery import BearerHeader
from src.connectors.mcp.providers.base import DiscoveredOAuth, MCPProvider
from src.connectors.mcp.resolved import HttpTarget

TAVILY_MCP_URL = "https://mcp.tavily.com/mcp/"

PROVIDER = MCPProvider(
    key="tavily",
    display_name="Tavily",
    description="Search the web and read pages, with sources, through Tavily.",
    icon="tavily",
    docs_url="https://docs.tavily.com/documentation/mcp",
    target=lambda install: HttpTarget(TAVILY_MCP_URL),
    # Tavily registers clients dynamically (RFC 7591) with PKCE, so signing in needs no API key or client of our own.
    oauth=DiscoveredOAuth(server_url=TAVILY_MCP_URL, delivery=BearerHeader()),
)
