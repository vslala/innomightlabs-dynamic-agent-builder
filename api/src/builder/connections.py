"""Accounts the person connects, asked for by the system rather than by Ila.

A blueprint's MCP connection (`kind: McpConnection`, `provider: tavily`) needs the person's own sign-in, which
only they can give, in their browser. When Ila plans a draft that uses a provider the account isn't connected
to, the system shows a card in the chat instead of the plan. The card's button calls `POST /builder/{id}/connect`,
which installs the preset (registering an OAuth client where the server allows it) and returns the sign-in
address for a popup window. Once the person is back, the next plan finds the connection and goes ahead.

Nothing here is specific to a provider: a preset that needs nothing typed in (`missing_inputs({})` is empty)
can be connected from the chat; one that needs set-up (its own OAuth app) is left to the Connectors page, and
the plan says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from pydantic import ValidationError

from src.blueprints.draft import Draft
from src.blueprints.kinds.mcp_connection import connection_for, is_ready
from src.blueprints.spec import McpConnectionSpec
from src.config import settings
from src.connectors.mcp.models import MCPProviderInstallRequest
from src.connectors.mcp.providers import PROVIDERS, get_provider
from src.connectors.mcp.repository import get_mcp_connection_repository
from src.connectors.mcp.service import MCPConnectorService

#: Where the provider sends the popup back to. The page finishes the sign-in and tells the chat.
POPUP_RETURN_PATH = "/dashboard/oauth/done"


@dataclass(frozen=True)
class ConnectionNeed:
    resource: str
    provider: str
    title: str
    description: str


def missing_connections(draft: Draft, user_email: str) -> list[ConnectionNeed]:
    """Every MCP connection in the draft that the person can connect from the chat and hasn't yet."""
    needs = []
    for name, raw in draft.kept("McpConnection"):
        try:
            spec = McpConnectionSpec.model_validate(raw)
        except ValidationError:
            continue  # the validator reports it to Ila
        connection = connection_for(spec, user_email)
        if connection is not None and is_ready(connection):
            continue
        preset = PROVIDERS.get(spec.provider or (connection.provider_key if connection else "") or "")
        if preset is None or preset.missing_inputs({}):
            continue  # not something the chat can connect; the plan explains
        needs.append(ConnectionNeed(
            resource=name, provider=preset.key, title=preset.display_name, description=preset.description
        ))
    return needs


def connect_request(need: ConnectionNeed, conversation_id: str) -> dict[str, Any]:
    """A `connect_request` payload: the chat shows it as a card with a Connect button."""
    return {
        "type": "connect_request",
        "connect": {
            "provider": need.provider,
            "title": f"Connect {need.title}",
            "description": f"{need.description} Sign in once and every agent you link can use it.",
            "conversation_id": conversation_id,
        },
    }


async def start_connection(service: MCPConnectorService, user_email: str, provider_key: str) -> Optional[str]:
    """The address to sign in at, installing the preset first if the account has no connection for it yet.
    None when it's already connected."""
    provider = get_provider(provider_key)
    if provider.missing_inputs({}):
        raise ValueError(f"{provider.display_name} needs setting up on the Connectors page first.")
    return_to = settings.frontend_url.rstrip("/") + POPUP_RETURN_PATH
    existing = [
        connection for connection in get_mcp_connection_repository().list_connections(user_email)
        if connection.provider_key == provider_key
    ]
    if any(is_ready(connection) for connection in existing):
        return None
    if existing:
        return service.start_oauth(owner_email=user_email, mcp_id=existing[0].mcp_id, return_to=return_to)
    installed = await service.install_provider(
        user_email, provider_key, MCPProviderInstallRequest(inputs={}, return_to=return_to)
    )
    return installed.authorize_url
