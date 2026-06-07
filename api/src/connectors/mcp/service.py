from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.agents.repository import AgentRepository
from src.connectors.mcp.client import MCPClientError, StreamableHTTPMCPClient
from src.connectors.mcp.models import (
    AgentMCPConnection,
    AgentMCPConnectionResponse,
    MCPApiKeyAuthConfig,
    MCPAuthType,
    MCPConnection,
    MCPConnectionCreateRequest,
    MCPConnectionResponse,
    MCPConnectionUpdateRequest,
    MCPOAuthDiscoveryResponse,
    MCPOAuthAuthConfig,
    MCPOAuthCredentials,
    MCPOAuthProviderConfig,
)
from src.connectors.mcp.oauth import (
    MCPOAuthError,
    build_authorization_url,
    build_credentials,
    canonical_resource_url,
    create_state_session,
    discover_oauth_provider,
    encode_state_session,
    exchange_code_for_tokens,
    generate_code_challenge,
    refresh_access_token,
)
from src.connectors.mcp.repository import MCPConnectionRepository, get_mcp_connection_repository
from src.crypto import decrypt, encrypt

log = logging.getLogger(__name__)


class MCPConnectorService:
    """Coordinates user MCP configuration, per-agent enablement, and runtime calls."""

    def __init__(
        self,
        *,
        repository: Optional[MCPConnectionRepository] = None,
        agent_repository: Optional[AgentRepository] = None,
        client: Optional[StreamableHTTPMCPClient] = None,
    ):
        self.repository = repository or get_mcp_connection_repository()
        self.agent_repository = agent_repository or AgentRepository()
        self.client = client or StreamableHTTPMCPClient()

    def create_connection(
        self,
        owner_email: str,
        request: MCPConnectionCreateRequest,
    ) -> MCPConnectionResponse:
        connection = MCPConnection(
            owner_email=owner_email,
            name=request.name.strip(),
            server_url=str(request.server_url),
            auth_type=request.auth_type,
            encrypted_auth_config=self._encrypt_auth_config(
                auth_type=request.auth_type,
                server_url=str(request.server_url),
                api_key=request.api_key,
                oauth=request.oauth,
            ),
            enabled=request.enabled,
        )
        saved = self.repository.save_connection(connection)
        log.info(
            "Created MCP connection mcp_id=%s owner=%s auth_type=%s server_url=%s",
            saved.mcp_id,
            owner_email,
            saved.auth_type.value,
            saved.server_url,
        )
        return self._connection_response(saved)

    def update_connection(
        self,
        owner_email: str,
        mcp_id: str,
        request: MCPConnectionUpdateRequest,
    ) -> MCPConnectionResponse:
        connection = self._require_connection(owner_email, mcp_id)
        existing_auth_type = connection.auth_type
        if request.name is not None:
            connection.name = request.name.strip()
        if request.server_url is not None:
            connection.server_url = str(request.server_url)
        if request.enabled is not None:
            connection.enabled = request.enabled
        if request.auth_type is not None:
            if request.auth_type == MCPAuthType.API_KEY and request.api_key is None:
                raise ValueError("api_key is required when changing MCP authentication to API key")
            if request.auth_type == MCPAuthType.OAUTH and request.oauth is None:
                raise ValueError("oauth is required when changing MCP authentication to OAuth")
            connection.auth_type = request.auth_type
        if request.api_key is not None:
            connection.encrypted_auth_config = self._encrypt_auth_config(
                auth_type=connection.auth_type,
                server_url=connection.server_url,
                api_key=request.api_key,
            )
        if request.oauth is not None:
            connection.encrypted_auth_config = self._encrypt_auth_config(
                auth_type=connection.auth_type,
                server_url=connection.server_url,
                oauth=request.oauth,
                previous=self._decrypt_oauth_auth(connection)
                if existing_auth_type == MCPAuthType.OAUTH
                else None,
            )
        saved = self.repository.save_connection(connection)
        log.info(
            "Updated MCP connection mcp_id=%s owner=%s auth_type=%s enabled=%s",
            saved.mcp_id,
            owner_email,
            saved.auth_type.value,
            saved.enabled,
        )
        return self._connection_response(saved)

    def list_connections(self, owner_email: str) -> list[MCPConnectionResponse]:
        return [
            self._connection_response(connection)
            for connection in self.repository.list_connections(owner_email)
        ]

    def get_connection(self, owner_email: str, mcp_id: str) -> MCPConnectionResponse:
        return self._connection_response(self._require_connection(owner_email, mcp_id))

    async def discover_oauth(self, server_url: str) -> MCPOAuthDiscoveryResponse:
        log.info("Discovering MCP OAuth metadata server_url=%s", server_url)
        discovered = await discover_oauth_provider(server_url)
        log.info(
            "Discovered MCP OAuth metadata resource_url=%s authorization_server=%s registered_client=%s",
            discovered.resource_url,
            discovered.authorization_server,
            discovered.registered_client,
        )
        return discovered

    def delete_connection(self, owner_email: str, mcp_id: str) -> None:
        self._require_connection(owner_email, mcp_id)
        self.repository.delete_connection(owner_email, mcp_id)

    def enable_for_agent(
        self,
        *,
        owner_email: str,
        agent_id: str,
        mcp_id: str,
        enabled: bool = True,
    ) -> AgentMCPConnectionResponse:
        agent = self.agent_repository.find_agent_by_id(agent_id, owner_email)
        if not agent:
            raise ValueError("Agent not found")
        connection = self._require_connection(owner_email, mcp_id)
        link = AgentMCPConnection(
            agent_id=agent_id,
            owner_email=owner_email,
            mcp_id=mcp_id,
            enabled=enabled,
        )
        saved = self.repository.save_agent_connection(link)
        return self._agent_response(saved, connection)

    def disable_for_agent(self, *, owner_email: str, agent_id: str, mcp_id: str) -> None:
        agent = self.agent_repository.find_agent_by_id(agent_id, owner_email)
        if not agent:
            raise ValueError("Agent not found")
        self.repository.delete_agent_connection(agent_id, mcp_id)

    def list_agent_connections(
        self,
        *,
        owner_email: str,
        agent_id: str,
        enabled_only: bool = False,
        verify_agent: bool = True,
    ) -> list[AgentMCPConnectionResponse]:
        if verify_agent:
            agent = self.agent_repository.find_agent_by_id(agent_id, owner_email)
            if not agent:
                raise ValueError("Agent not found")

        responses: list[AgentMCPConnectionResponse] = []
        for link in self.repository.list_agent_connections(agent_id):
            if link.owner_email != owner_email:
                continue
            if enabled_only and not link.enabled:
                continue
            connection = self.repository.find_connection(owner_email, link.mcp_id)
            if not connection or not connection.enabled:
                continue
            responses.append(self._agent_response(link, connection))
        return responses

    def build_system_prompt_addendum(self, enabled_connections: list[AgentMCPConnectionResponse]) -> str:
        if not enabled_connections:
            return ""

        lines = [
            "<mcp_connectors>",
            "You can use external MCP connectors through two tools: list_mcp_tools and call_mcp_tool.",
            "Call list_mcp_tools before call_mcp_tool when you need available tool names or input schemas.",
            "Use the exact mcp_id and tool_name returned by list_mcp_tools.",
        ]
        for connection in enabled_connections:
            lines.append(f"- {connection.mcp_id}: {connection.name}")
        lines.append("</mcp_connectors>")
        return "\n".join(lines)

    async def list_runtime_tools(
        self,
        *,
        owner_email: str,
        agent_id: str,
        mcp_id: str | None = None,
    ) -> dict[str, Any]:
        connections = self._runtime_connections(owner_email=owner_email, agent_id=agent_id, mcp_id=mcp_id)
        results: list[dict[str, Any]] = []
        for connection in connections:
            try:
                auth_headers = await self._auth_headers_for_connection(connection)
                tools_result = await self.client.list_tools(connection, auth_headers)
                log.info(
                    "Listed MCP tools mcp_id=%s agent_id=%s tool_count=%s",
                    connection.mcp_id,
                    agent_id,
                    len(tools_result.get("tools", [])) if isinstance(tools_result.get("tools"), list) else 0,
                )
                results.append(
                    {
                        "mcp_id": connection.mcp_id,
                        "name": connection.name,
                        "tools": tools_result.get("tools", []),
                    }
                )
            except Exception as exc:
                log.warning(
                    "Failed to list MCP tools mcp_id=%s agent_id=%s auth_type=%s error=%s",
                    connection.mcp_id,
                    agent_id,
                    connection.auth_type.value,
                    exc,
                    exc_info=True,
                )
                results.append(
                    {
                        "mcp_id": connection.mcp_id,
                        "name": connection.name,
                        "error": str(exc),
                        "tools": [],
                    }
                )
        return {"connectors": results}

    async def call_runtime_tool(
        self,
        *,
        owner_email: str,
        agent_id: str,
        mcp_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        connections = self._runtime_connections(owner_email=owner_email, agent_id=agent_id, mcp_id=mcp_id)
        if not connections:
            raise ValueError(f"MCP connector '{mcp_id}' is not enabled for this agent")
        connection = connections[0]
        auth_headers = await self._auth_headers_for_connection(connection)
        try:
            result = await self.client.call_tool(
                connection,
                auth_headers,
                tool_name=tool_name,
                arguments=arguments,
            )
            log.info(
                "Called MCP tool mcp_id=%s agent_id=%s tool_name=%s",
                connection.mcp_id,
                agent_id,
                tool_name,
            )
            return result
        except MCPClientError:
            log.warning(
                "Failed to call MCP tool mcp_id=%s agent_id=%s tool_name=%s",
                connection.mcp_id,
                agent_id,
                tool_name,
                exc_info=True,
            )
            raise

    def start_oauth(self, *, owner_email: str, mcp_id: str, return_to: str) -> str:
        connection = self._require_connection(owner_email, mcp_id)
        if connection.auth_type != MCPAuthType.OAUTH:
            raise ValueError("MCP connector is not configured for OAuth")

        auth = self._decrypt_oauth_auth(connection)
        log.info(
            "Starting MCP OAuth mcp_id=%s owner=%s resource_url=%s token_url=%s",
            mcp_id,
            owner_email,
            auth.provider.resource_url,
            auth.provider.token_url,
        )
        session = create_state_session(user_email=owner_email, mcp_id=mcp_id, return_to=return_to)
        state = encode_state_session(session)
        return build_authorization_url(
            provider=auth.provider,
            state=state,
            code_challenge=generate_code_challenge(session.code_verifier),
        )

    async def complete_oauth(
        self,
        *,
        owner_email: str,
        mcp_id: str,
        code: str,
        code_verifier: str,
    ) -> MCPConnectionResponse:
        connection = self._require_connection(owner_email, mcp_id)
        if connection.auth_type != MCPAuthType.OAUTH:
            raise ValueError("MCP connector is not configured for OAuth")

        auth = self._decrypt_oauth_auth(connection)
        tokens = await exchange_code_for_tokens(
            provider=auth.provider,
            code=code,
            code_verifier=code_verifier,
        )
        credentials = build_credentials(tokens, default_scope=auth.provider.scope)
        log.info(
            "Completed MCP OAuth mcp_id=%s owner=%s expires_at=%s has_refresh_token=%s",
            mcp_id,
            owner_email,
            credentials.expires_at.isoformat(),
            bool(credentials.refresh_token),
        )
        connection.encrypted_auth_config = self._encrypt_oauth_auth(
            MCPOAuthAuthConfig(provider=auth.provider, credentials=credentials)
        )
        saved = self.repository.save_connection(connection)
        return self._connection_response(saved)

    def _runtime_connections(
        self,
        *,
        owner_email: str,
        agent_id: str,
        mcp_id: str | None = None,
    ) -> list[MCPConnection]:
        links = self.repository.list_agent_connections(agent_id)
        connections: list[MCPConnection] = []
        for link in links:
            if link.owner_email != owner_email or not link.enabled:
                continue
            if mcp_id and link.mcp_id != mcp_id:
                continue
            connection = self.repository.find_connection(owner_email, link.mcp_id)
            if connection and connection.enabled:
                connections.append(connection)
        return connections

    def _agent_response(
        self,
        link: AgentMCPConnection,
        connection: MCPConnection,
    ) -> AgentMCPConnectionResponse:
        return AgentMCPConnectionResponse(
            agent_id=link.agent_id,
            mcp_id=link.mcp_id,
            name=connection.name,
            server_url=connection.server_url,
            enabled=link.enabled and connection.enabled,
            created_at=link.created_at,
            updated_at=link.updated_at,
        )

    def _connection_response(self, connection: MCPConnection) -> MCPConnectionResponse:
        oauth_connected = False
        if connection.auth_type == MCPAuthType.OAUTH:
            try:
                oauth_connected = self._decrypt_oauth_auth(connection).credentials is not None
            except ValueError:
                oauth_connected = False

        return MCPConnectionResponse(
            mcp_id=connection.mcp_id,
            name=connection.name,
            server_url=connection.server_url,
            transport=connection.transport,
            auth_type=connection.auth_type,
            oauth_connected=oauth_connected,
            enabled=connection.enabled,
            created_at=connection.created_at,
            updated_at=connection.updated_at,
        )

    def _require_connection(self, owner_email: str, mcp_id: str) -> MCPConnection:
        connection = self.repository.find_connection(owner_email, mcp_id)
        if not connection:
            raise ValueError("MCP connection not found")
        return connection

    def _encrypt_auth_config(
        self,
        *,
        auth_type: MCPAuthType,
        server_url: str,
        api_key: Optional[MCPApiKeyAuthConfig] = None,
        oauth: Optional[MCPOAuthProviderConfig] = None,
        previous: Optional[MCPOAuthAuthConfig] = None,
    ) -> str:
        if auth_type == MCPAuthType.API_KEY:
            if api_key is None:
                raise ValueError("api_key is required for API key MCP authentication")
            return encrypt(api_key.model_dump_json())

        if auth_type == MCPAuthType.OAUTH:
            if oauth is None:
                raise ValueError("oauth is required for OAuth MCP authentication")
            if not oauth.resource_url:
                oauth = oauth.model_copy(update={"resource_url": canonical_resource_url(server_url)})
            return self._encrypt_oauth_auth(
                MCPOAuthAuthConfig(provider=oauth, credentials=previous.credentials if previous else None)
            )

        raise ValueError(f"Unsupported MCP authentication type: {auth_type}")

    def _encrypt_oauth_auth(self, auth: MCPOAuthAuthConfig) -> str:
        return encrypt(auth.model_dump_json())

    def _decrypt_api_key_auth(self, connection: MCPConnection) -> MCPApiKeyAuthConfig:
        if connection.auth_type != MCPAuthType.API_KEY:
            raise ValueError("MCP connector is not configured for API key authentication")
        return MCPApiKeyAuthConfig.model_validate(json.loads(decrypt(connection.encrypted_auth_config)))

    def _decrypt_oauth_auth(self, connection: MCPConnection) -> MCPOAuthAuthConfig:
        if connection.auth_type != MCPAuthType.OAUTH:
            raise ValueError("MCP connector is not configured for OAuth")
        return MCPOAuthAuthConfig.model_validate(json.loads(decrypt(connection.encrypted_auth_config)))

    async def _auth_headers_for_connection(self, connection: MCPConnection) -> dict[str, str]:
        if connection.auth_type == MCPAuthType.API_KEY:
            auth = self._decrypt_api_key_auth(connection)
            return {header.name: header.value for header in auth.headers}

        if connection.auth_type == MCPAuthType.OAUTH:
            credentials = await self._ensure_valid_oauth_credentials(connection)
            return {"Authorization": f"{_normalize_token_type(credentials.token_type)} {credentials.access_token}"}

        raise ValueError(f"Unsupported MCP authentication type: {connection.auth_type}")

    async def _ensure_valid_oauth_credentials(self, connection: MCPConnection) -> MCPOAuthCredentials:
        auth = self._decrypt_oauth_auth(connection)
        if not auth.credentials:
            log.warning("MCP OAuth credentials missing mcp_id=%s", connection.mcp_id)
            raise ValueError("MCP OAuth connector has not been connected yet")

        if not auth.credentials.refresh_token:
            if auth.credentials.expires_at <= datetime.now(timezone.utc):
                log.warning(
                    "MCP OAuth credentials expired without refresh token mcp_id=%s expires_at=%s",
                    connection.mcp_id,
                    auth.credentials.expires_at.isoformat(),
                )
                raise ValueError("MCP OAuth connector credentials expired. Reconnect the connector.")
            return auth.credentials

        if not auth.credentials.is_expiring_soon():
            return auth.credentials

        try:
            log.info(
                "Refreshing MCP OAuth token mcp_id=%s expires_at=%s",
                connection.mcp_id,
                auth.credentials.expires_at.isoformat(),
            )
            tokens = await refresh_access_token(
                provider=auth.provider,
                refresh_token=auth.credentials.refresh_token,
            )
            credentials = build_credentials(
                tokens,
                previous=auth.credentials,
                default_scope=auth.provider.scope,
            )
        except MCPOAuthError:
            log.exception("Failed to refresh MCP OAuth token for connector %s", connection.mcp_id)
            raise

        connection.encrypted_auth_config = self._encrypt_oauth_auth(
            MCPOAuthAuthConfig(provider=auth.provider, credentials=credentials)
        )
        self.repository.save_connection(connection)
        log.info(
            "Refreshed MCP OAuth token mcp_id=%s expires_at=%s has_refresh_token=%s",
            connection.mcp_id,
            credentials.expires_at.isoformat(),
            bool(credentials.refresh_token),
        )
        return credentials


def _normalize_token_type(token_type: str) -> str:
    return "Bearer" if token_type.strip().lower() == "bearer" else token_type.strip()


def get_mcp_connector_service() -> MCPConnectorService:
    return MCPConnectorService()
