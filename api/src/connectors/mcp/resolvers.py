from __future__ import annotations

import json
from typing import Protocol

from src.connectors.mcp.delivery import BearerHeader
from src.connectors.mcp.models import (
    MCPApiKeyAuthConfig,
    MCPAuthType,
    MCPConnection,
    MCPOAuthAuthConfig,
    MCPOAuthCredentials,
)
from src.connectors.mcp.resolved import HttpTarget, OAuthBinding, ResolvedConnection
from src.crypto import decrypt, encrypt


class ConnectionResolver(Protocol):
    """Turns a stored connection into what the runtime needs to open it."""

    def resolve(self, connection: MCPConnection) -> ResolvedConnection: ...

    def store_oauth_credentials(self, connection: MCPConnection, credentials: MCPOAuthCredentials) -> str:
        """Return the connection's new encrypted_auth_config with these credentials stored."""
        ...


class CustomResolver:
    """Connections the user configured by hand."""

    def resolve(self, connection: MCPConnection) -> ResolvedConnection:
        if connection.auth_type == MCPAuthType.OAUTH:
            return ResolvedConnection(
                target=HttpTarget(connection.server_url),
                oauth=OAuthBinding(auth=self.oauth_auth(connection), delivery=BearerHeader()),
            )
        if connection.auth_type == MCPAuthType.API_KEY:
            headers = {header.name: header.value for header in self.api_key_auth(connection).headers}
            return ResolvedConnection(target=HttpTarget(connection.server_url, headers))
        return ResolvedConnection(target=HttpTarget(connection.server_url))

    def store_oauth_credentials(self, connection: MCPConnection, credentials: MCPOAuthCredentials) -> str:
        auth = self.oauth_auth(connection)
        return encrypt(MCPOAuthAuthConfig(provider=auth.provider, credentials=credentials).model_dump_json())

    def api_key_auth(self, connection: MCPConnection) -> MCPApiKeyAuthConfig:
        if connection.auth_type != MCPAuthType.API_KEY:
            raise ValueError("MCP connector is not configured for API key authentication")
        return MCPApiKeyAuthConfig.model_validate(json.loads(decrypt(connection.encrypted_auth_config)))

    def oauth_auth(self, connection: MCPConnection) -> MCPOAuthAuthConfig:
        if connection.auth_type != MCPAuthType.OAUTH:
            raise ValueError("MCP connector is not configured for OAuth")
        return MCPOAuthAuthConfig.model_validate(json.loads(decrypt(connection.encrypted_auth_config)))
