from __future__ import annotations

from src.connectors.mcp.delivery import BearerHeader
from src.connectors.mcp.providers.base import DiscoveredOAuth, MCPProvider
from src.connectors.mcp.resolved import HttpTarget

STRIPE_MCP_URL = "https://mcp.stripe.com"

PROVIDER = MCPProvider(
    key="stripe",
    display_name="Stripe",
    description="Look up customers, payments and subscriptions in Stripe.",
    icon="stripe",
    category="payments",
    featured=True,
    tags=("payments", "billing", "invoices", "subscriptions", "customers", "refunds"),
    docs_url="https://docs.stripe.com/mcp",
    target=lambda install: HttpTarget(STRIPE_MCP_URL),
    # Stripe registers clients dynamically and its public clients use PKCE, so signing in needs no client of our own.
    oauth=DiscoveredOAuth(server_url=STRIPE_MCP_URL, delivery=BearerHeader()),
)
