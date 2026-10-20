from __future__ import annotations

from src.connectors.mcp.delivery import BearerHeader
from src.connectors.mcp.providers.base import DiscoveredOAuth, MCPProvider
from src.connectors.mcp.resolved import HttpTarget

SUPABASE_MCP_URL = "https://mcp.supabase.com/mcp"

PROVIDER = MCPProvider(
    key="supabase",
    display_name="Supabase",
    description="Manage and query your Supabase projects and databases.",
    icon="supabase",
    category="development",
    featured=True,
    tags=("postgres", "database", "sql", "backend", "auth"),
    docs_url="https://supabase.com/docs/guides/ai-tools/mcp",
    target=lambda install: HttpTarget(SUPABASE_MCP_URL),
    oauth=DiscoveredOAuth(server_url=SUPABASE_MCP_URL, delivery=BearerHeader()),
)
