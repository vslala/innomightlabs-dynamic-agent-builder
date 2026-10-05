from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from src.agents.repository import AgentRepository
from src.connectors.mcp.client import MCPClientError, StreamableHTTPMCPClient, _sanitize_response_text
from src.connectors.mcp.disclaimer import DISCLAIMER_VERSION, sharing_disclaimer
from src.connectors.mcp.models import (
    AgentMCPConnection,
    AgentMCPConnectionResponse,
    MCPApiKeyAuthConfig,
    MCPAuthType,
    MCPCaller,
    MCPCatalogTool,
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
    MCPRuntimeStatusResponse,
    MCPSharingDisclaimer,
    MCPSharingSummary,
    MCPSharingUpdateRequest,
    MCPSharingView,
    MCPStdioPackageResponse,
    MCPStdioStoredConfig,
    MCPToolCatalog,
    MCPToolCatalogResponse,
    MCPTransport,
    validate_stdio_auth,
)
from src.auth.oauth_handoff import safe_return_to
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
from src.connectors.mcp.resolved import HttpTarget, MCPTarget, OAuthBinding, StdioTarget
from src.connectors.mcp.resolvers import ConnectionResolver, CustomResolver
from src.connectors.mcp.sidecar import StdioMCPSidecarClient
from src.connectors.mcp.usage import (
    MAX_ERROR_CHARS,
    MCPCall,
    MCPUsageRepository,
    arguments_preview,
    get_mcp_usage_repository,
    reported_error,
)
from src.crypto import encrypt
from src.form_models import Form
from src.skills.models import ActorKind

log = logging.getLogger(__name__)

# How long a tool call waits for a hosted server that is still starting (the sidecar allows up to 60).
RUNTIME_START_WAIT_SECONDS = 45
# How long signing in may wait on a server to list its tools before we leave it to the share dialog.
CATALOG_CAPTURE_SECONDS = 15


class MCPConnectorService:
    """Coordinates user MCP configuration, per-agent enablement, and runtime calls."""

    def __init__(
        self,
        *,
        repository: Optional[MCPConnectionRepository] = None,
        agent_repository: Optional[AgentRepository] = None,
        client: Optional[StreamableHTTPMCPClient] = None,
        sidecar: Optional[StdioMCPSidecarClient] = None,
        usage: Optional[MCPUsageRepository] = None,
    ):
        self.repository = repository or get_mcp_connection_repository()
        self.usage = usage or get_mcp_usage_repository()
        self.agent_repository = agent_repository or AgentRepository()
        self.client = client or StreamableHTTPMCPClient()
        self.sidecar = sidecar or StdioMCPSidecarClient()
        self.custom = CustomResolver()
        self.providers = ProviderResolver()

    def create_connection(
        self,
        owner_email: str,
        request: MCPConnectionCreateRequest,
    ) -> MCPConnectionResponse:
        if request.transport == MCPTransport.STDIO:
            return self._create_stdio_connection(owner_email, request)
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

    async def update_connection(
        self,
        owner_email: str,
        mcp_id: str,
        request: MCPConnectionUpdateRequest,
    ) -> MCPConnectionResponse:
        connection = self._require_connection(owner_email, mcp_id)
        if connection.provider_key:
            response = self._update_provider_install(connection, request)
        elif connection.transport == MCPTransport.STDIO:
            response = self._update_stdio_connection(connection, request)
        else:
            response = self._update_http_connection(connection, request)
        if request.enabled is False:
            await self._release(connection)
        return response

    def _update_http_connection(
        self,
        connection: MCPConnection,
        request: MCPConnectionUpdateRequest,
    ) -> MCPConnectionResponse:
        if request.inputs is not None:
            raise ValueError("inputs can only be updated on catalog connectors")
        if request.stdio is not None or request.oauth_delivery is not None:
            raise ValueError("stdio and oauth_delivery apply only to stdio MCP servers")
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
            saved.owner_email,
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

    async def delete_connection(self, owner_email: str, mcp_id: str) -> None:
        connection = self._require_connection(owner_email, mcp_id)
        self.repository.delete_connection(owner_email, mcp_id)
        await self._release(connection)

    async def list_stdio_packages(self) -> list[MCPStdioPackageResponse]:
        return await self.sidecar.packages()

    async def runtime_status(self, owner_email: str, mcp_id: str) -> MCPRuntimeStatusResponse:
        connection = self._require_stdio_connection(owner_email, mcp_id)
        status = await self.sidecar.status(connection.mcp_id)
        if status is None:
            return MCPRuntimeStatusResponse(state="stopped")
        return self._public_status(status)

    async def restart_runtime(self, owner_email: str, mcp_id: str) -> MCPRuntimeStatusResponse:
        connection = self._require_stdio_connection(owner_email, mcp_id)
        if not connection.enabled:
            raise ValueError("Enable the MCP connector before starting it")
        target = await self._prepared_target(connection)
        if not isinstance(target, StdioTarget):
            raise ValueError("MCP connector is not a stdio server")
        await self.sidecar.delete(connection.mcp_id)
        status = await self.sidecar.ensure(connection.mcp_id, target, wait_seconds=0)
        log.info("Restarted hosted MCP server mcp_id=%s state=%s", connection.mcp_id, status.state)
        return self._public_status(status)

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
        existing = self.repository.find_agent_connection(agent_id, mcp_id)
        link = existing or AgentMCPConnection(agent_id=agent_id, owner_email=owner_email, mcp_id=mcp_id)
        saved = self.repository.save_agent_connection(link.model_copy(update={"enabled": enabled}))
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
        actor_kind: ActorKind,
        enabled_only: bool = False,
        verify_agent: bool = True,
    ) -> list[AgentMCPConnectionResponse]:
        if verify_agent:
            agent = self.agent_repository.find_agent_by_id(agent_id, owner_email)
            if not agent:
                raise ValueError("Agent not found")

        responses: list[AgentMCPConnectionResponse] = []
        for link in self.repository.list_agent_connections(agent_id):
            if link.owner_email != owner_email or not link.usable_by(actor_kind):
                continue
            if enabled_only and not link.enabled:
                continue
            connection = self.repository.find_connection(owner_email, link.mcp_id)
            if not connection or not connection.enabled:
                continue
            responses.append(self._agent_response(link, connection))
        return responses

    async def refresh_tool_catalog(self, owner_email: str, mcp_id: str) -> MCPToolCatalog:
        connection = self._require_connection(owner_email, mcp_id)
        target, headers = await self._session(connection)
        listed = await self.client.list_tools(target, headers)
        catalog = MCPToolCatalog(
            owner_email=owner_email,
            mcp_id=mcp_id,
            tools=[MCPCatalogTool.from_server(tool) for tool in listed.get("tools", []) if tool.get("name")],
        )
        return self.repository.save_tool_catalog(catalog)

    async def capture_tool_catalog(self, owner_email: str, mcp_id: str) -> None:
        """Snapshot the tools when the owner signs in or enables a connector. A miss costs nothing:
        the share dialog lists them live when there is no snapshot."""
        try:
            await asyncio.wait_for(self.refresh_tool_catalog(owner_email, mcp_id), CATALOG_CAPTURE_SECONDS)
        except Exception as exc:
            log.warning("Could not capture MCP tool catalog mcp_id=%s error=%r", mcp_id, exc)

    async def sharing_view(self, *, owner_email: str, agent_id: str, mcp_id: str) -> MCPSharingView:
        link, connection = self._require_agent_link(owner_email=owner_email, agent_id=agent_id, mcp_id=mcp_id)
        catalog = self.repository.find_tool_catalog(owner_email, mcp_id)
        catalog_error: str | None = None
        if catalog is None:
            # Connectors set up before sharing existed have no snapshot yet.
            try:
                catalog = await self.refresh_tool_catalog(owner_email, mcp_id)
            except Exception as exc:
                log.warning("Could not list tools to share mcp_id=%s error=%r", mcp_id, exc)
                catalog_error = f"Couldn't reach {connection.name} to list its tools. Check the connector and retry."
        return self._sharing_view(link, connection, catalog, catalog_error)

    def share(
        self,
        *,
        owner_email: str,
        agent_id: str,
        mcp_id: str,
        request: MCPSharingUpdateRequest,
    ) -> MCPSharingView:
        link, connection = self._require_agent_link(owner_email=owner_email, agent_id=agent_id, mcp_id=mcp_id)
        catalog = self.repository.find_tool_catalog(owner_email, mcp_id)
        saved = self.repository.save_agent_connection(link.shared(request, catalog, by=owner_email))
        log.info(
            "Updated MCP sharing mcp_id=%s agent_id=%s available_to=%s tools=%s",
            mcp_id,
            agent_id,
            [kind.value for kind in saved.sharing.available_to],
            len(saved.sharing.allowed_tools),
        )
        return self._sharing_view(saved, connection, catalog)

    async def list_runtime_tools(
        self,
        *,
        owner_email: str,
        agent_id: str,
        caller: MCPCaller,
        mcp_id: str | None = None,
    ) -> dict[str, Any]:
        runtime = self._runtime_connections(owner_email=owner_email, agent_id=agent_id, caller=caller, mcp_id=mcp_id)
        results: list[dict[str, Any]] = []
        for link, connection in runtime:
            try:
                target, headers = await self._session(connection)
                tools_result = await self.client.list_tools(target, headers)
                listed = tools_result.get("tools")
                if not isinstance(listed, list):
                    listed = []
                log.info(
                    "Listed MCP tools mcp_id=%s agent_id=%s tool_count=%s",
                    connection.mcp_id,
                    agent_id,
                    len(listed),
                )
                results.append(
                    {
                        "mcp_id": connection.mcp_id,
                        "name": connection.name,
                        "tools": link.offered_tools(caller.actor_kind, listed),
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
        caller: MCPCaller,
        mcp_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        runtime = self._runtime_connections(owner_email=owner_email, agent_id=agent_id, caller=caller, mcp_id=mcp_id)
        not_enabled = f"MCP connector '{mcp_id}' is not enabled for this agent"
        if not runtime:
            raise ValueError(not_enabled)
        link, connection = runtime[0]
        # An unshared tool gets the same answer as a missing connector, so nobody can probe what exists.
        if not link.allows(caller.actor_kind, tool_name):
            raise ValueError(not_enabled)

        started = time.monotonic()
        error: str | None = None
        try:
            target, headers = await self._session(connection)
            result = await self.client.call_tool(
                target,
                headers,
                tool_name=tool_name,
                arguments=arguments,
            )
            error = reported_error(result)
            log.info(
                "Called MCP tool mcp_id=%s agent_id=%s tool_name=%s actor_kind=%s",
                connection.mcp_id,
                agent_id,
                tool_name,
                caller.actor_kind.value,
            )
            return result
        except Exception as exc:
            error = str(exc)[:MAX_ERROR_CHARS]
            log.warning(
                "Failed to call MCP tool mcp_id=%s agent_id=%s tool_name=%s",
                connection.mcp_id,
                agent_id,
                tool_name,
                exc_info=True,
            )
            raise
        finally:
            await self._record(
                MCPCall(
                    agent_id=agent_id,
                    mcp_id=connection.mcp_id,
                    connection_name=connection.name,
                    tool_name=tool_name,
                    actor_kind=caller.actor_kind,
                    actor_id=caller.actor_id,
                    actor_email=caller.actor_email,
                    conversation_id=caller.conversation_id,
                    arguments_preview=arguments_preview(arguments),
                    success=error is None,
                    error=error,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            )

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
        session = create_state_session(user_email=owner_email, mcp_id=mcp_id, return_to=safe_return_to(return_to))
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
        caller: MCPCaller,
        mcp_id: str | None = None,
    ) -> list[tuple[AgentMCPConnection, MCPConnection]]:
        runtime: list[tuple[AgentMCPConnection, MCPConnection]] = []
        for link in self.repository.list_agent_connections(agent_id):
            if link.owner_email != owner_email or not link.enabled or not link.usable_by(caller.actor_kind):
                continue
            if mcp_id and link.mcp_id != mcp_id:
                continue
            connection = self.repository.find_connection(owner_email, link.mcp_id)
            if connection and connection.enabled:
                runtime.append((link, connection))
        return runtime

    def _require_agent_link(
        self, *, owner_email: str, agent_id: str, mcp_id: str
    ) -> tuple[AgentMCPConnection, MCPConnection]:
        if not self.agent_repository.find_agent_by_id(agent_id, owner_email):
            raise ValueError("Agent not found")
        link = self.repository.find_agent_connection(agent_id, mcp_id)
        if not link or link.owner_email != owner_email:
            raise ValueError("MCP connector not found for this agent")
        return link, self._require_connection(owner_email, mcp_id)

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
            sharing=MCPSharingSummary.of(link.sharing),
            created_at=link.created_at,
            updated_at=link.updated_at,
        )

    def _sharing_view(
        self,
        link: AgentMCPConnection,
        connection: MCPConnection,
        catalog: MCPToolCatalog | None,
        catalog_error: str | None = None,
    ) -> MCPSharingView:
        return MCPSharingView(
            agent_id=link.agent_id,
            mcp_id=link.mcp_id,
            connection_name=connection.name,
            sharing=link.sharing,
            catalog=MCPToolCatalogResponse(tools=catalog.tools, fetched_at=catalog.fetched_at) if catalog else None,
            catalog_error=catalog_error,
            disclaimer=MCPSharingDisclaimer(
                version=DISCLAIMER_VERSION, paragraphs=sharing_disclaimer(connection.name)
            ),
        )

    async def _record(self, call: MCPCall) -> None:
        """Telemetry: a failed write is logged, never passed on to the tool call."""
        try:
            await asyncio.to_thread(self.usage.record, call)
        except Exception as exc:
            log.warning("Failed to record MCP call mcp_id=%s agent_id=%s error=%r", call.mcp_id, call.agent_id, exc)

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
        elif connection.transport == MCPTransport.STDIO:
            stored = self.custom.stdio_config(connection)
            response.stdio = stored.target.summary()
            response.oauth_delivery = stored.oauth_delivery
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

    async def _prepared_target(self, connection: MCPConnection) -> MCPTarget:
        """Resolve a connection and apply fresh OAuth credentials through its delivery."""
        resolved = self._resolver(connection).resolve(connection)
        if resolved.oauth is None:
            return resolved.target
        credentials = await self._fresh_credentials(connection, resolved.oauth)
        return resolved.oauth.delivery.apply(resolved.target, resolved.oauth.auth.provider, credentials)

    async def _session(self, connection: MCPConnection) -> tuple[MCPConnection, dict[str, str]]:
        """Return the connection copy and headers the Streamable HTTP client should use."""
        # The client addresses servers by connection.server_url and logs mcp_id/name, so it gets a copy
        # pointing at the real endpoint: the remote server, or the sidecar's façade for a hosted one.
        match await self._prepared_target(connection):
            case HttpTarget(url=url, headers=headers):
                return connection.model_copy(update={"server_url": url}), headers
            case StdioTarget() as stdio:
                status = await self.sidecar.ensure(
                    connection.mcp_id, stdio, wait_seconds=RUNTIME_START_WAIT_SECONDS
                )
                if status.state != "running":
                    raise MCPClientError(status.failure_message())
                return (
                    connection.model_copy(update={"server_url": self.sidecar.endpoint_url(connection.mcp_id)}),
                    self.sidecar.auth_headers(),
                )
        raise ValueError(f"Unsupported MCP target for connector {connection.mcp_id}")

    async def _release(self, connection: MCPConnection) -> None:
        """Stop a hosted server's process. Remote servers have nothing to release."""
        if connection.transport != MCPTransport.STDIO:
            return
        try:
            await self.sidecar.delete(connection.mcp_id)
        except MCPClientError:
            log.warning("Failed to stop hosted MCP server mcp_id=%s", connection.mcp_id, exc_info=True)

    def _require_stdio_connection(self, owner_email: str, mcp_id: str) -> MCPConnection:
        connection = self._require_connection(owner_email, mcp_id)
        if connection.transport != MCPTransport.STDIO:
            raise ValueError("Only hosted stdio MCP connectors have a runtime")
        return connection

    def _public_status(self, status: MCPRuntimeStatusResponse) -> MCPRuntimeStatusResponse:
        # Servers may print credentials on stderr; redact the patterns the HTTP client already redacts.
        return status.model_copy(update={"stderr_tail": _sanitize_response_text_keeping_lines(status.stderr_tail)})

    def _create_stdio_connection(
        self,
        owner_email: str,
        request: MCPConnectionCreateRequest,
    ) -> MCPConnectionResponse:
        assert request.stdio is not None
        oauth = (
            MCPOAuthAuthConfig(provider=request.oauth)
            if request.auth_type == MCPAuthType.OAUTH and request.oauth is not None
            else None
        )
        stored = MCPStdioStoredConfig(target=request.stdio, oauth=oauth, oauth_delivery=request.oauth_delivery)
        connection = self.repository.save_connection(
            MCPConnection(
                owner_email=owner_email,
                name=request.name.strip(),
                server_url="",
                transport=MCPTransport.STDIO,
                auth_type=request.auth_type,
                encrypted_auth_config=encrypt(stored.model_dump_json()),
                enabled=request.enabled,
            )
        )
        log.info(
            "Created stdio MCP connection mcp_id=%s owner=%s package=%s auth_type=%s",
            connection.mcp_id,
            owner_email,
            request.stdio.package,
            connection.auth_type.value,
        )
        return self._connection_response(connection)

    def _update_stdio_connection(
        self,
        connection: MCPConnection,
        request: MCPConnectionUpdateRequest,
    ) -> MCPConnectionResponse:
        if request.inputs is not None:
            raise ValueError("inputs can only be updated on catalog connectors")
        if request.server_url is not None or request.api_key is not None:
            raise ValueError("stdio MCP servers take credentials through env, not server_url or api_key headers")
        stored = self.custom.stdio_config(connection)
        target = request.stdio.keeping_values_from(stored.target) if request.stdio else stored.target
        missing = target.missing_values()
        if missing:
            raise ValueError(f"Environment variables need values: {', '.join(missing)}")
        auth_type = request.auth_type or connection.auth_type
        provider = request.oauth or (stored.oauth.provider if stored.oauth else None)
        delivery = request.oauth_delivery or stored.oauth_delivery
        if auth_type != MCPAuthType.OAUTH:
            provider, delivery = None, None
        validate_stdio_auth(auth_type, target, provider, delivery)

        credentials = stored.oauth.credentials if stored.oauth and request.oauth is None else None
        if stored.oauth and request.oauth is not None and stored.oauth.provider.client_id == request.oauth.client_id:
            # Same client: keep the user signed in while endpoints or scopes are corrected.
            credentials = stored.oauth.credentials
        oauth = MCPOAuthAuthConfig(provider=provider, credentials=credentials) if provider else None
        connection.encrypted_auth_config = encrypt(
            MCPStdioStoredConfig(target=target, oauth=oauth, oauth_delivery=delivery).model_dump_json()
        )
        connection.auth_type = auth_type
        if request.name is not None:
            connection.name = request.name.strip()
        if request.enabled is not None:
            connection.enabled = request.enabled
        saved = self.repository.save_connection(connection)
        log.info("Updated stdio MCP connection mcp_id=%s auth_type=%s", saved.mcp_id, saved.auth_type.value)
        return self._connection_response(saved)

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


def _sanitize_response_text_keeping_lines(text: str) -> str:
    return "\n".join(_sanitize_response_text(line) for line in text.splitlines())
