from __future__ import annotations

from src.connectors.mcp.delivery import BearerHeader
from src.connectors.mcp.providers.base import DiscoveredOAuth, MCPProvider, oauth_client_inputs
from src.connectors.mcp.resolved import HttpTarget

HUBSPOT_MCP_URL = "https://mcp.hubspot.com"

PROVIDER = MCPProvider(
    key="hubspot",
    display_name="HubSpot",
    description="Search and read contacts, companies and deals in HubSpot.",
    icon="hubspot",
    category="marketing",
    featured=True,
    tags=("crm", "contacts", "companies", "deals", "sales", "marketing"),
    docs_url="https://developers.hubspot.com/docs/apps/developer-platform/build-apps/integrate-with-the-remote-hubspot-mcp-server",
    inputs=oauth_client_inputs("HubSpot → Development → MCP Auth Apps"),
    target=lambda install: HttpTarget(HUBSPOT_MCP_URL),
    # HubSpot has no dynamic registration: the user creates an MCP auth app. Scopes follow the tools the server offers.
    oauth=DiscoveredOAuth(server_url=HUBSPOT_MCP_URL, delivery=BearerHeader(), register_client=False),
)
