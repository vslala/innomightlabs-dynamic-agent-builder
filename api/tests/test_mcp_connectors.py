from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import httpx

from src.agents.models import Agent
from src.agents.runtime_state import AgentTurnState
from src.agents.tool_execution import ToolExecutionRouter
from src.connectors.mcp.client import MCP_SESSION_HEADER, StreamableHTTPMCPClient
from src.connectors.mcp.models import (
    AgentMCPConnection,
    MCPApiKeyAuthConfig,
    MCPAuthType,
    MCPConnection,
    MCPConnectionCreateRequest,
    MCPOAuthAuthConfig,
    MCPOAuthCredentials,
    MCPOAuthProviderConfig,
    MCPToolCallRequest,
)
from src.connectors.mcp.oauth import (
    authorization_server_metadata_url,
    canonical_resource_url,
    discover_oauth_provider,
    protected_resource_metadata_url,
)
from src.connectors.mcp.service import MCPConnectorService
from src.crypto import encrypt


class FakeMCPRepository:
    def __init__(self):
        self.connections: dict[tuple[str, str], MCPConnection] = {}
        self.agent_connections: dict[tuple[str, str], AgentMCPConnection] = {}

    def save_connection(self, connection: MCPConnection) -> MCPConnection:
        self.connections[(connection.owner_email, connection.mcp_id)] = connection
        return connection

    def find_connection(self, owner_email: str, mcp_id: str) -> MCPConnection | None:
        return self.connections.get((owner_email, mcp_id))

    def list_connections(self, owner_email: str) -> list[MCPConnection]:
        return [
            connection
            for (email, _), connection in self.connections.items()
            if email == owner_email
        ]

    def delete_connection(self, owner_email: str, mcp_id: str) -> None:
        self.connections.pop((owner_email, mcp_id), None)

    def save_agent_connection(self, link: AgentMCPConnection) -> AgentMCPConnection:
        self.agent_connections[(link.agent_id, link.mcp_id)] = link
        return link

    def find_agent_connection(self, agent_id: str, mcp_id: str) -> AgentMCPConnection | None:
        return self.agent_connections.get((agent_id, mcp_id))

    def list_agent_connections(self, agent_id: str) -> list[AgentMCPConnection]:
        return [
            link
            for (stored_agent_id, _), link in self.agent_connections.items()
            if stored_agent_id == agent_id
        ]

    def delete_agent_connection(self, agent_id: str, mcp_id: str) -> None:
        self.agent_connections.pop((agent_id, mcp_id), None)


class FakeAgentRepository:
    def __init__(self, agent: Agent):
        self.agent = agent

    def find_agent_by_id(self, agent_id: str, created_by: str) -> Agent | None:
        if self.agent.agent_id == agent_id and self.agent.created_by == created_by:
            return self.agent
        return None


class FakeMCPClient:
    def __init__(self):
        self.list_calls: list[str] = []
        self.tool_calls: list[dict[str, Any]] = []

    async def list_tools(self, connection: MCPConnection, auth_headers: dict[str, str]) -> dict[str, Any]:
        self.list_calls.append(connection.mcp_id)
        assert auth_headers == {
            "Authorization": "Bearer secret",
            "X-Ahrefs-Client": "innomightlabs",
        }
        return {
            "tools": [
                {
                    "name": "site_audit",
                    "description": "Audit a website",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                    },
                }
            ]
        }

    async def call_tool(
        self,
        connection: MCPConnection,
        auth_headers: dict[str, str],
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        self.tool_calls.append(
            {"mcp_id": connection.mcp_id, "tool_name": tool_name, "arguments": arguments}
        )
        assert auth_headers == {
            "Authorization": "Bearer secret",
            "X-Ahrefs-Client": "innomightlabs",
        }
        return {"content": [{"type": "text", "text": "SEO audit complete"}]}


class FakeOAuthMCPClient:
    def __init__(self):
        self.auth_headers: list[dict[str, str]] = []

    async def list_tools(self, connection: MCPConnection, auth_headers: dict[str, str]) -> dict[str, Any]:
        self.auth_headers.append(auth_headers)
        return {"tools": [{"name": "search_pages", "description": "Search pages"}]}

    async def call_tool(
        self,
        connection: MCPConnection,
        auth_headers: dict[str, str],
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        self.auth_headers.append(auth_headers)
        return {"content": [{"type": "text", "text": "Page found"}]}


class FakeSkillRuntime:
    async def handle_tool_call(self, **_: Any) -> str:
        return "unused"


class FakeNativeTools:
    async def execute(self, tool_name: str, tool_input: dict[str, Any], agent_id: str) -> str:
        return f"native:{tool_name}:{agent_id}:{tool_input}"


def make_agent() -> Agent:
    return Agent(
        agent_id="agent-1",
        agent_name="SEO Agent",
        agent_architecture="krishna-memgpt",
        agent_provider="OpenAI",
        agent_model="gpt-5.5",
        agent_persona="SEO analyst",
        created_by="owner@example.com",
        created_at=datetime.now(timezone.utc),
    )


def make_service() -> tuple[MCPConnectorService, FakeMCPRepository, FakeMCPClient]:
    agent = make_agent()
    repository = FakeMCPRepository()
    client = FakeMCPClient()
    service = MCPConnectorService(
        repository=repository,  # type: ignore[arg-type]
        agent_repository=FakeAgentRepository(agent),  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
    )
    return service, repository, client


def create_connection(service: MCPConnectorService) -> str:
    response = service.create_connection(
        "owner@example.com",
        MCPConnectionCreateRequest.model_validate(
            {
                "name": "Ahrefs",
                "server_url": "https://mcp.ahrefs.example/mcp",
                "api_key": {
                    "headers": [
                        {"name": "Authorization", "value": "Bearer secret"},
                        {"name": "X-Ahrefs-Client", "value": "innomightlabs"},
                    ]
                },
            }
        ),
    )
    return response.mcp_id


def test_mcp_auth_config_accepts_legacy_single_header_shape() -> None:
    config = MCPApiKeyAuthConfig.model_validate(
        {"header_name": "Authorization", "header_value": "Bearer legacy"}
    )

    assert config.headers[0].name == "Authorization"
    assert config.headers[0].value == "Bearer legacy"


def test_mcp_connection_can_be_enabled_per_agent() -> None:
    service, _repository, _client = make_service()
    mcp_id = create_connection(service)

    linked = service.enable_for_agent(
        owner_email="owner@example.com",
        agent_id="agent-1",
        mcp_id=mcp_id,
        enabled=True,
    )

    assert linked.mcp_id == mcp_id
    assert linked.name == "Ahrefs"
    assert linked.enabled is True
    assert service.list_agent_connections(owner_email="owner@example.com", agent_id="agent-1")


def test_oauth_mcp_connection_is_created_without_credentials() -> None:
    service, _repository, _client = make_service()

    response = service.create_connection(
        "owner@example.com",
        MCPConnectionCreateRequest.model_validate(
            {
                "name": "Notion MCP",
                "server_url": "https://mcp.notion.example/mcp",
                "auth_type": "oauth",
                "oauth": {
                    "authorization_url": "https://notion.example/oauth/authorize",
                    "token_url": "https://notion.example/oauth/token",
                    "client_id": "client-1",
                    "client_secret": "secret",
                    "scope": "read write",
                },
            }
        ),
    )

    assert response.auth_type == "oauth"
    assert response.oauth_connected is False


def test_mcp_oauth_discovery_urls_follow_standard_locations() -> None:
    resource_url = canonical_resource_url("https://MCP.Notion.com/mcp/")

    assert resource_url == "https://mcp.notion.com/mcp"
    assert protected_resource_metadata_url(resource_url) == "https://mcp.notion.com/.well-known/oauth-protected-resource"
    assert (
        authorization_server_metadata_url("https://auth.example.com/tenant")
        == "https://auth.example.com/.well-known/oauth-authorization-server/tenant"
    )


@pytest.mark.asyncio
async def test_mcp_oauth_discovery_maps_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_json(url: str) -> dict[str, Any]:
        if url == "https://mcp.notion.example/.well-known/oauth-protected-resource":
            return {"authorization_servers": ["https://auth.notion.example"]}
        if url == "https://auth.notion.example/.well-known/oauth-authorization-server":
            return {
                "authorization_endpoint": "https://auth.notion.example/oauth/authorize",
                "token_endpoint": "https://auth.notion.example/oauth/token",
                "registration_endpoint": "https://auth.notion.example/oauth/register",
                "scopes_supported": ["read", "write"],
            }
        raise AssertionError(f"Unexpected discovery URL {url}")

    async def fake_register_client(registration_endpoint: str, scope: str) -> dict[str, Any]:
        assert registration_endpoint == "https://auth.notion.example/oauth/register"
        assert scope == "read write"
        return {"client_id": "registered-client", "client_secret": "registered-secret"}

    monkeypatch.setattr("src.connectors.mcp.oauth._fetch_json", fake_fetch_json)
    monkeypatch.setattr("src.connectors.mcp.oauth._register_client", fake_register_client)

    discovered = await discover_oauth_provider("https://mcp.notion.example/mcp")

    assert discovered.authorization_url == "https://auth.notion.example/oauth/authorize"
    assert discovered.token_url == "https://auth.notion.example/oauth/token"
    assert discovered.resource_url == "https://mcp.notion.example/mcp"
    assert discovered.client_id == "registered-client"
    assert discovered.client_secret == "registered-secret"
    assert discovered.registered_client is True


@pytest.mark.asyncio
async def test_oauth_mcp_runtime_uses_bearer_token() -> None:
    agent = make_agent()
    repository = FakeMCPRepository()
    client = FakeOAuthMCPClient()
    service = MCPConnectorService(
        repository=repository,  # type: ignore[arg-type]
        agent_repository=FakeAgentRepository(agent),  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
    )
    auth = MCPOAuthAuthConfig(
        provider=MCPOAuthProviderConfig.model_validate(
            {
                "authorization_url": "https://notion.example/oauth/authorize",
                "token_url": "https://notion.example/oauth/token",
                "client_id": "client-1",
                "scope": "read",
            }
        ),
        credentials=MCPOAuthCredentials(
            access_token="oauth-token",
            refresh_token=None,
            expires_at=datetime.now(timezone.utc).replace(year=2099),
        ),
    )
    connection = repository.save_connection(
        MCPConnection(
            owner_email="owner@example.com",
            name="Notion MCP",
            server_url="https://mcp.notion.example/mcp",
            auth_type=MCPAuthType.OAUTH,
            encrypted_auth_config=encrypt(auth.model_dump_json()),
        )
    )
    service.enable_for_agent(
        owner_email="owner@example.com",
        agent_id="agent-1",
        mcp_id=connection.mcp_id,
        enabled=True,
    )

    listed = await service.list_runtime_tools(owner_email="owner@example.com", agent_id="agent-1")

    assert listed["connectors"][0]["tools"][0]["name"] == "search_pages"
    assert client.auth_headers == [{"Authorization": "Bearer oauth-token"}]


@pytest.mark.asyncio
async def test_oauth_mcp_runtime_rejects_expired_token_without_refresh() -> None:
    agent = make_agent()
    repository = FakeMCPRepository()
    client = FakeOAuthMCPClient()
    service = MCPConnectorService(
        repository=repository,  # type: ignore[arg-type]
        agent_repository=FakeAgentRepository(agent),  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
    )
    auth = MCPOAuthAuthConfig(
        provider=MCPOAuthProviderConfig.model_validate(
            {
                "authorization_url": "https://notion.example/oauth/authorize",
                "token_url": "https://notion.example/oauth/token",
                "client_id": "client-1",
                "resource_url": "https://mcp.notion.example/mcp",
            }
        ),
        credentials=MCPOAuthCredentials(
            access_token="expired-token",
            refresh_token=None,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        ),
    )
    connection = repository.save_connection(
        MCPConnection(
            owner_email="owner@example.com",
            name="Notion MCP",
            server_url="https://mcp.notion.example/mcp",
            auth_type=MCPAuthType.OAUTH,
            encrypted_auth_config=encrypt(auth.model_dump_json()),
        )
    )
    service.enable_for_agent(
        owner_email="owner@example.com",
        agent_id="agent-1",
        mcp_id=connection.mcp_id,
        enabled=True,
    )

    listed = await service.list_runtime_tools(owner_email="owner@example.com", agent_id="agent-1")

    assert "credentials expired" in listed["connectors"][0]["error"]
    assert client.auth_headers == []


@pytest.mark.asyncio
async def test_mcp_runtime_lists_and_calls_live_tools() -> None:
    service, _repository, client = make_service()
    mcp_id = create_connection(service)
    service.enable_for_agent(
        owner_email="owner@example.com",
        agent_id="agent-1",
        mcp_id=mcp_id,
        enabled=True,
    )

    listed = await service.list_runtime_tools(
        owner_email="owner@example.com",
        agent_id="agent-1",
    )
    called = await service.call_runtime_tool(
        owner_email="owner@example.com",
        agent_id="agent-1",
        mcp_id=mcp_id,
        tool_name="site_audit",
        arguments={"url": "https://example.com"},
    )

    assert listed["connectors"][0]["tools"][0]["name"] == "site_audit"
    assert called["content"][0]["text"] == "SEO audit complete"
    assert client.list_calls == [mcp_id]
    assert client.tool_calls == [
        {"mcp_id": mcp_id, "tool_name": "site_audit", "arguments": {"url": "https://example.com"}}
    ]


@pytest.mark.asyncio
async def test_tool_execution_router_dispatches_mcp_tools() -> None:
    service, _repository, _client = make_service()
    mcp_id = create_connection(service)
    service.enable_for_agent(
        owner_email="owner@example.com",
        agent_id="agent-1",
        mcp_id=mcp_id,
        enabled=True,
    )
    router = ToolExecutionRouter(
        skill_runtime=FakeSkillRuntime(),
        native_tools=FakeNativeTools(),
        mcp_runtime=service,
    )
    state = AgentTurnState(
        owner_email="owner@example.com",
        actor_email="owner@example.com",
        actor_id="owner@example.com",
        conversation_id="conversation-1",
        agent_id="agent-1",
        provider_name="OpenAI",
        model_name="gpt-5.5",
        user_message="Audit my site",
    )

    outcome = await router.execute(
        tool_name="call_mcp_tool",
        tool_input=MCPToolCallRequest(
            mcp_id=mcp_id,
            tool_name="site_audit",
            arguments={"url": "https://example.com"},
        ).model_dump(),
        tool_use_id="tool-1",
        state=state,
    )

    assert outcome.success is True
    assert json.loads(outcome.result)["content"][0]["text"] == "SEO audit complete"


def test_streamable_http_client_decodes_sse_json_rpc_response() -> None:
    response = type(
        "Response",
        (),
        {
            "headers": {"content-type": "text/event-stream"},
            "text": 'event: message\ndata: {"jsonrpc":"2.0","result":{"tools":[]}}\n\n',
        },
    )()

    decoded = StreamableHTTPMCPClient()._decode_response(response)

    assert decoded == {"jsonrpc": "2.0", "result": {"tools": []}}


@pytest.mark.asyncio
async def test_streamable_http_client_initializes_session_before_list_tools() -> None:
    seen_methods: list[str] = []
    session_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        method = payload["method"]
        seen_methods.append(method)
        session_headers.append(request.headers.get(MCP_SESSION_HEADER))
        if method == "initialize":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "notion", "version": "1.0.0"},
                    },
                },
                headers={MCP_SESSION_HEADER: "session-123"},
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": payload["id"], "result": {"tools": []}},
            )
        raise AssertionError(f"Unexpected MCP method {method}")

    connection = MCPConnection(
        owner_email="owner@example.com",
        name="Notion MCP",
        server_url="https://mcp.notion.example/mcp",
        encrypted_auth_config="unused",
    )
    client = StreamableHTTPMCPClient(transport=httpx.MockTransport(handler))

    result = await client.list_tools(connection, {"Authorization": "Bearer token"})

    assert result == {"tools": []}
    assert seen_methods == ["initialize", "notifications/initialized", "tools/list"]
    assert session_headers == [None, "session-123", "session-123"]
