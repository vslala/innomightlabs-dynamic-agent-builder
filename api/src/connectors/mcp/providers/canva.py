from __future__ import annotations

from src.connectors.mcp.delivery import BearerHeader
from src.connectors.mcp.providers.base import DiscoveredOAuth, MCPProvider, oauth_client_inputs
from src.connectors.mcp.resolved import HttpTarget

CANVA_MCP_URL = "https://mcp.canva.com/mcp"

PROVIDER = MCPProvider(
    key="canva",
    display_name="Canva",
    description="Create and edit designs in the user's Canva account.",
    icon="canva",
    docs_url="https://www.canva.dev/docs/apps/mcp/",
    inputs=oauth_client_inputs("the Canva Developer Portal"),
    target=lambda install: HttpTarget(CANVA_MCP_URL),
    oauth=DiscoveredOAuth(server_url=CANVA_MCP_URL, delivery=BearerHeader(), register_client=False),
)
