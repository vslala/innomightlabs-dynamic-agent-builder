from __future__ import annotations

import logging
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
    MCPProviderInstallRequest,
    MCPProviderInstallResponse,
    MCPProviderResponse,
)
from src.connectors.mcp.oauth import (
    MCPOAuthError,
    build_authorization_url,
    build_credentials,
    canonical_resource_url,
    create_state_session,
    discover_authorization_server,
    discover_oauth_provider,
    encode_state_session,
    exchange_code_for_tokens,
    generate_code_challenge,
    refresh_access_token,
)
from src.connectors.mcp.providers import PROVIDERS, get_provider
from src.connectors.mcp.providers.base import DiscoveredOAuth, MCPProvider, ProviderInstall
from src.connectors.mcp.providers.resolver import ProviderInstallSecrets, ProviderResolver
from src.connectors.mcp.repository import MCPConnectionRepository, get_mcp_connection_repository
from src.connectors.mcp.resolved import HttpTarget, OAuthBinding
from src.connectors.mcp.resolvers import ConnectionResolver, CustomResolver
from src.crypto import encrypt
from src.form_models import Form

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
        self.custom = CustomResolver()
        self.providers = ProviderResolver()

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
        if connection.provider_key:
            return self._update_provider_install(connection, request)
        if request.inputs is not None:
            raise ValueError("inputs can only be updated on catalog connectors")
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
                previous=self.custom.oauth_auth(connection)
                if existing_auth_type == MCPAuthType.OAUTH
                else None,
            )
        if request.auth_type == MCPAuthType.NONE:
            connection.encrypted_auth_config = self._encrypt_auth_config(
                auth_type=MCPAuthType.NONE,
                server_url=connection.server_url,
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

    def list_providers(self, owner_email: str) -> list[MCPProviderResponse]:
        installed: dict[str, int] = {}
        for connection in self.repository.list_connections(owner_email):
            if connection.provider_key:
                installed[connection.provider_key] = installed.get(connection.provider_key, 0) + 1
        return [
            MCPProviderResponse(
                key=provider.key,
                display_name=provider.display_name,
                description=provider.description,
                icon=provider.icon,
                docs_url=provider.docs_url,
                transport=provider.transport,
                has_inputs=bool(provider.inputs),
                has_sign_in=provider.oauth is not None,
                installed_count=installed.get(provider.key, 0),
            )
            for provider in PROVIDERS.values()
        ]

    def provider_install_form(self, key: str) -> Form:
        provider = get_provider(key)
        return Form(
            form_name="install",
            submit_path=f"/connectors/mcp/providers/{provider.key}/install",
            form_inputs=list(provider.inputs),
        )

    def connection_settings_form(self, owner_email: str, mcp_id: str) -> Form:
        connection = self._require_connection(owner_email, mcp_id)
        provider = get_provider(connection.provider_key)
        values = self._public_inputs(connection, provider)
        return Form(
            form_name="settings",
            submit_path=f"/connectors/mcp/{mcp_id}",
            form_inputs=[
                field.model_copy(update={"value": values.get(field.name, field.value)})
                if field.name in values
                else field
                for field in provider.inputs
            ],
        )

    async def install_provider(
        self,
        owner_email: str,
        key: str,
        request: MCPProviderInstallRequest,
    ) -> MCPProviderInstallResponse:
        provider = get_provider(key)
        secrets = ProviderInstallSecrets(inputs=provider.validated_inputs(request.inputs))
        if isinstance(provider.oauth, DiscoveredOAuth):
            discovered = await discover_oauth_provider(
                provider.oauth.server_url,
                register_client=provider.oauth.register_client,
            )
            if provider.oauth.register_client and not discovered.registered_client:
                raise ValueError(f"{provider.display_name} did not register an OAuth client. Try again later.")
            config = discovered.model_dump(
                include={
                    "authorization_url",
                    "token_url",
                    "client_id",
                    "client_secret",
                    "scope",
                    "resource_url",
                    "client_registration",
                }
            )
            if not provider.oauth.register_client:
                # Without registration the client is the user's own; the resolver re-applies it from inputs on
                # every use, so later edits to the client take effect.
                install = ProviderInstall(inputs=secrets.inputs)
                config.update(client_id=install.oauth_client_id, client_secret=install.oauth_client_secret)
            secrets.oauth_provider = MCPOAuthProviderConfig.model_validate(config)

        connection = self.repository.save_connection(
            MCPConnection(
                owner_email=owner_email,
                name=(request.name or provider.display_name).strip(),
                server_url="",
                transport=provider.transport,
                auth_type=provider.auth_type(),
                encrypted_auth_config=secrets.encrypted(),
                provider_key=provider.key,
            )
        )
        log.info(
            "Installed MCP provider provider=%s mcp_id=%s owner=%s",
            provider.key,
            connection.mcp_id,
            owner_email,
        )
        authorize_url = (
            self.start_oauth(owner_email=owner_email, mcp_id=connection.mcp_id, return_to=request.return_to)
            if provider.oauth is not None
            else None
        )
        return MCPProviderInstallResponse(
            connection=self._connection_response(connection),
            authorize_url=authorize_url,
        )

    def _update_provider_install(
        self,
        connection: MCPConnection,
        request: MCPConnectionUpdateRequest,
    ) -> MCPConnectionResponse:
        if request.changes_connection_config():
            raise ValueError("Catalog connectors are configured by their provider; only name, inputs and enabled can change")
        provider = get_provider(connection.provider_key)
        if request.name is not None:
            connection.name = request.name.strip()
        if request.enabled is not None:
            connection.enabled = request.enabled
        if request.inputs is not None:
            secrets = ProviderInstallSecrets.of(connection)
            submitted = dict(request.inputs)
            for name in provider.secret_input_names():
                if not submitted.get(name, "").strip() and secrets.inputs.get(name):
                    submitted[name] = secrets.inputs[name]
            secrets.inputs = provider.validated_inputs(submitted)
            connection.encrypted_auth_config = secrets.encrypted()
        saved = self.repository.save_connection(connection)
        log.info("Updated MCP provider install mcp_id=%s provider=%s", saved.mcp_id, provider.key)
        return self._connection_response(saved)

    def _public_inputs(self, connection: MCPConnection, provider: MCPProvider) -> dict[str, str]:
        secret_names = provider.secret_input_names()
        return {
            name: value
            for name, value in ProviderInstallSecrets.of(connection).inputs.items()
            if name not in secret_names
        }

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

    async def discover_oauth_issuer(self, issuer_url: str) -> MCPOAuthDiscoveryResponse:
        log.info("Discovering OAuth authorization server issuer_url=%s", issuer_url)
        return await discover_authorization_server(issuer_url)

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
                target, headers = await self._session(connection)
                tools_result = await self.client.list_tools(target, headers)
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
        target, headers = await self._session(connection)
        try:
            result = await self.client.call_tool(
                target,
                headers,
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
        oauth = self._oauth_binding(connection)
        log.info(
            "Starting MCP OAuth mcp_id=%s owner=%s resource_url=%s token_url=%s",
            mcp_id,
            owner_email,
            oauth.auth.provider.resource_url,
            oauth.auth.provider.token_url,
        )
        session = create_state_session(user_email=owner_email, mcp_id=mcp_id, return_to=return_to)
        state = encode_state_session(session)
        return build_authorization_url(
            provider=oauth.auth.provider,
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
        oauth = self._oauth_binding(connection)
        tokens = await exchange_code_for_tokens(
            provider=oauth.auth.provider,
            code=code,
            code_verifier=code_verifier,
        )
        credentials = build_credentials(tokens, default_scope=oauth.auth.provider.scope)
        log.info(
            "Completed MCP OAuth mcp_id=%s owner=%s expires_at=%s has_refresh_token=%s",
            mcp_id,
            owner_email,
            credentials.expires_at.isoformat() if credentials.expires_at else "never",
            bool(credentials.refresh_token),
        )
        connection.encrypted_auth_config = self._resolver(connection).store_oauth_credentials(connection, credentials)
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
                oauth_connected = self._oauth_binding(connection).auth.credentials is not None
            except ValueError:
                oauth_connected = False

        response = MCPConnectionResponse(
            mcp_id=connection.mcp_id,
            name=connection.name,
            server_url=connection.server_url,
            transport=connection.transport,
            auth_type=connection.auth_type,
            oauth_connected=oauth_connected,
            enabled=connection.enabled,
            created_at=connection.created_at,
            updated_at=connection.updated_at,
            provider_key=connection.provider_key,
        )
        if connection.provider_key and connection.provider_key in PROVIDERS:
            provider = PROVIDERS[connection.provider_key]
            response.setup_state = self.providers.setup_state(connection)
            response.inputs = self._public_inputs(connection, provider)
        return response

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
        if auth_type == MCPAuthType.NONE:
            return encrypt("{}")

        if auth_type == MCPAuthType.API_KEY:
            if api_key is None:
                raise ValueError("api_key is required for API key MCP authentication")
            return encrypt(api_key.model_dump_json())

        if auth_type == MCPAuthType.OAUTH:
            if oauth is None:
                raise ValueError("oauth is required for OAuth MCP authentication")
            if not oauth.resource_url:
                oauth = oauth.model_copy(update={"resource_url": canonical_resource_url(server_url)})
            return encrypt(
                MCPOAuthAuthConfig(
                    provider=oauth,
                    credentials=previous.credentials if previous else None,
                ).model_dump_json()
            )

        raise ValueError(f"Unsupported MCP authentication type: {auth_type}")

    def _resolver(self, connection: MCPConnection) -> ConnectionResolver:
        return self.providers if connection.provider_key else self.custom

    def _oauth_binding(self, connection: MCPConnection) -> OAuthBinding:
        oauth = self._resolver(connection).resolve(connection).oauth
        if oauth is None:
            raise ValueError("MCP connector is not configured for OAuth")
        return oauth

    async def _session(self, connection: MCPConnection) -> tuple[MCPConnection, dict[str, str]]:
        """Resolve a connection, apply fresh OAuth credentials, and return the client's target and headers."""
        resolved = self._resolver(connection).resolve(connection)
        target = resolved.target
        if resolved.oauth:
            credentials = await self._fresh_credentials(connection, resolved.oauth)
            target = resolved.oauth.delivery.apply(target, resolved.oauth.auth.provider, credentials)

        match target:
            case HttpTarget(url=url, headers=headers):
                # The client addresses servers by connection.server_url and logs mcp_id/name.
                return connection.model_copy(update={"server_url": url}), headers
        raise ValueError(f"Unsupported MCP target for connector {connection.mcp_id}")

    async def _fresh_credentials(self, connection: MCPConnection, oauth: OAuthBinding) -> MCPOAuthCredentials:
        credentials = oauth.auth.credentials
        if not credentials:
            log.warning("MCP OAuth credentials missing mcp_id=%s", connection.mcp_id)
            raise ValueError("MCP OAuth connector has not been connected yet")

        if not credentials.refresh_token:
            if credentials.is_expired():
                log.warning(
                    "MCP OAuth credentials expired without refresh token mcp_id=%s expires_at=%s",
                    connection.mcp_id,
                    credentials.expires_at.isoformat() if credentials.expires_at else "never",
                )
                raise ValueError("MCP OAuth connector credentials expired. Reconnect the connector.")
            return credentials

        if not credentials.is_expiring_soon(oauth.delivery.refresh_buffer_seconds):
            return credentials

        provider = oauth.auth.provider
        try:
            log.info(
                "Refreshing MCP OAuth token mcp_id=%s expires_at=%s",
                connection.mcp_id,
                credentials.expires_at.isoformat() if credentials.expires_at else "never",
            )
            tokens = await refresh_access_token(provider=provider, refresh_token=credentials.refresh_token)
            refreshed = build_credentials(tokens, previous=credentials, default_scope=provider.scope)
        except MCPOAuthError:
            log.exception("Failed to refresh MCP OAuth token for connector %s", connection.mcp_id)
            raise

        connection.encrypted_auth_config = self._resolver(connection).store_oauth_credentials(connection, refreshed)
        self.repository.save_connection(connection)
        log.info(
            "Refreshed MCP OAuth token mcp_id=%s expires_at=%s has_refresh_token=%s",
            connection.mcp_id,
            refreshed.expires_at.isoformat() if refreshed.expires_at else "never",
            bool(refreshed.refresh_token),
        )
        return refreshed


def get_mcp_connector_service() -> MCPConnectorService:
    return MCPConnectorService()
