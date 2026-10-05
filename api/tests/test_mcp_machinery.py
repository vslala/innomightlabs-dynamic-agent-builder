from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from pydantic import ValidationError

from src.connectors.mcp.client import StreamableHTTPMCPClient
from src.connectors.mcp.delivery import (
    AccessTokenEnv,
    BearerHeader,
    GoogleAuthorizedUserFile,
    stdio_oauth_delivery,
)
from src.connectors.mcp.models import (
    MCPAuthType,
    MCPConnection,
    MCPConnectionCreateRequest,
    MCPOAuthAuthConfig,
    MCPOAuthCredentials,
    MCPOAuthDiscoveryRequest,
    MCPOAuthProviderConfig,
)
from src.connectors.mcp.oauth import (
    build_authorization_url,
    build_credentials,
    discover_authorization_server,
    exchange_code_for_tokens,
)
from src.connectors.mcp.resolved import HttpTarget, OAuthBinding, StdioTarget
from src.connectors.mcp.service import MCPConnectorService
from src.crypto import encrypt
from tests.test_mcp_connectors import (
    OWNER_CALLER,
    FakeMCPUsage,
    FakeAgentRepository,
    FakeMCPRepository,
    FakeOAuthMCPClient,
    make_agent,
)

OWNER = "owner@example.com"


def _provider(**overrides: Any) -> MCPOAuthProviderConfig:
    return MCPOAuthProviderConfig.model_validate(
        {
            "authorization_url": "https://auth.example/authorize",
            "token_url": "https://auth.example/token",
            "client_id": "client-1",
            "client_secret": "secret-1",
            "scope": "read",
            **overrides,
        }
    )


def _service(client: Any) -> tuple[MCPConnectorService, FakeMCPRepository]:
    repository = FakeMCPRepository()
    service = MCPConnectorService(
        repository=repository,  # type: ignore[arg-type]
        agent_repository=FakeAgentRepository(make_agent()),  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
        usage=FakeMCPUsage(),  # type: ignore[arg-type]
    )
    return service, repository


def _save_oauth_connection(
    service: MCPConnectorService,
    repository: FakeMCPRepository,
    credentials: MCPOAuthCredentials,
) -> MCPConnection:
    connection = repository.save_connection(
        MCPConnection(
            owner_email=OWNER,
            name="GitHub",
            server_url="https://mcp.github.example/mcp",
            auth_type=MCPAuthType.OAUTH,
            encrypted_auth_config=encrypt(
                MCPOAuthAuthConfig(provider=_provider(), credentials=credentials).model_dump_json()
            ),
        )
    )
    service.enable_for_agent(owner_email=OWNER, agent_id="agent-1", mcp_id=connection.mcp_id)
    return connection


# --- Token expiry -----------------------------------------------------------------------------


def test_token_without_expiry_or_refresh_token_never_expires() -> None:
    credentials = build_credentials({"access_token": "gho_token", "token_type": "bearer"})

    assert credentials.expires_at is None
    assert credentials.is_expired() is False
    assert credentials.is_expiring_soon(300) is False


def test_token_with_refresh_token_but_no_expiry_assumes_an_hour() -> None:
    credentials = build_credentials({"access_token": "token", "refresh_token": "refresh"})

    assert credentials.expires_at is not None
    remaining = (credentials.expires_at - datetime.now(timezone.utc)).total_seconds()
    assert 3590 < remaining <= 3600


def test_token_with_expires_in_uses_it() -> None:
    credentials = build_credentials({"access_token": "token", "expires_in": 120})

    assert credentials.expires_at is not None
    assert (credentials.expires_at - datetime.now(timezone.utc)).total_seconds() <= 120


def test_stored_credentials_with_expiry_still_load() -> None:
    stored = json.dumps(
        {"access_token": "token", "refresh_token": None, "expires_at": "2099-01-01T00:00:00+00:00"}
    )

    credentials = MCPOAuthCredentials.model_validate_json(stored)

    assert credentials.expires_at == datetime(2099, 1, 1, tzinfo=timezone.utc)
    assert credentials.is_expired() is False


@pytest.mark.asyncio
async def test_runtime_uses_non_expiring_token_after_an_hour() -> None:
    client = FakeOAuthMCPClient()
    service, repository = _service(client)
    _save_oauth_connection(
        service,
        repository,
        MCPOAuthCredentials(access_token="gho_token", refresh_token=None, expires_at=None),
    )

    listed = await service.list_runtime_tools(owner_email=OWNER, agent_id="agent-1", caller=OWNER_CALLER)

    assert "error" not in listed["connectors"][0]
    assert client.auth_headers == [{"Authorization": "Bearer gho_token"}]


# --- Refresh buffer comes from the delivery ---------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_buffer_comes_from_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    refreshes: list[str] = []

    async def fake_refresh(*, provider: MCPOAuthProviderConfig, refresh_token: str) -> dict[str, Any]:
        refreshes.append(refresh_token)
        return {"access_token": "fresh-token", "expires_in": 3600}

    monkeypatch.setattr("src.connectors.mcp.service.refresh_access_token", fake_refresh)
    service, repository = _service(FakeOAuthMCPClient())
    credentials = MCPOAuthCredentials(
        access_token="old-token",
        refresh_token="refresh-1",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=200),
    )
    connection = _save_oauth_connection(service, repository, credentials)
    auth = MCPOAuthAuthConfig(provider=_provider(), credentials=credentials)

    kept = await service._fresh_credentials(connection, OAuthBinding(auth=auth, delivery=BearerHeader()))
    refreshed = await service._fresh_credentials(
        connection, OAuthBinding(auth=auth, delivery=AccessTokenEnv(env_name="TOKEN"))
    )

    assert kept.access_token == "old-token"
    assert refreshed.access_token == "fresh-token"
    assert refreshes == ["refresh-1"]
    stored = service.custom.oauth_auth(repository.find_connection(OWNER, connection.mcp_id))  # type: ignore[arg-type]
    assert stored.credentials is not None and stored.credentials.access_token == "fresh-token"


# --- Deliveries -------------------------------------------------------------------------------


def _credentials(refresh_token: str | None = "refresh-1") -> MCPOAuthCredentials:
    return MCPOAuthCredentials(access_token="access-1", refresh_token=refresh_token)


def test_bearer_header_delivery_sets_authorization() -> None:
    target = BearerHeader().apply(HttpTarget("https://mcp.example", {"X-Other": "1"}), _provider(), _credentials())

    assert target == HttpTarget("https://mcp.example", {"X-Other": "1", "Authorization": "Bearer access-1"})


def test_access_token_env_delivery_sets_env_var() -> None:
    target = AccessTokenEnv(env_name="GITHUB_TOKEN").apply(StdioTarget("github"), _provider(), _credentials())

    assert isinstance(target, StdioTarget)
    assert target.env == {"GITHUB_TOKEN": "access-1"}


def test_google_authorized_user_file_uses_the_users_client_and_refresh_token() -> None:
    target = GoogleAuthorizedUserFile().apply(StdioTarget("google_ads"), _provider(), _credentials())

    assert isinstance(target, StdioTarget)
    assert json.loads(target.files["GOOGLE_APPLICATION_CREDENTIALS"]) == {
        "type": "authorized_user",
        "client_id": "client-1",
        "client_secret": "secret-1",
        "refresh_token": "refresh-1",
    }


def test_google_authorized_user_file_requires_refresh_token() -> None:
    with pytest.raises(ValueError, match="refresh token"):
        GoogleAuthorizedUserFile().apply(StdioTarget("google_ads"), _provider(), _credentials(refresh_token=None))


def test_delivery_rejects_the_wrong_transport() -> None:
    with pytest.raises(ValueError, match="cannot be used"):
        BearerHeader().apply(StdioTarget("google_ads"), _provider(), _credentials())
    with pytest.raises(ValueError, match="cannot be used"):
        AccessTokenEnv(env_name="TOKEN").apply(HttpTarget("https://mcp.example"), _provider(), _credentials())


def test_stdio_delivery_is_selected_by_name() -> None:
    assert stdio_oauth_delivery("access_token_env", "TOKEN") == AccessTokenEnv(env_name="TOKEN")
    assert stdio_oauth_delivery("google_authorized_user_file", "CREDS") == GoogleAuthorizedUserFile(env_name="CREDS")
    with pytest.raises(ValueError, match="Unsupported"):
        stdio_oauth_delivery("bearer_header", "TOKEN")


# --- OAuth parameters -------------------------------------------------------------------------


def test_authorization_url_omits_empty_resource_and_adds_provider_params() -> None:
    provider = _provider(authorization_params={"access_type": "offline", "prompt": "consent"})

    query = parse_qs(urlparse(build_authorization_url(provider=provider, state="s", code_challenge="c")).query)

    assert "resource" not in query
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]


def test_authorization_url_keeps_resource_for_remote_servers() -> None:
    provider = _provider(resource_url="https://mcp.example/mcp")

    query = parse_qs(urlparse(build_authorization_url(provider=provider, state="s", code_challenge="c")).query)

    assert query["resource"] == ["https://mcp.example/mcp"]


@pytest.mark.asyncio
async def test_code_exchange_omits_empty_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    posted: list[dict[str, str]] = []

    async def fake_post_token(token_url: str, data: dict[str, str]) -> dict[str, Any]:
        posted.append(data)
        return {"access_token": "token"}

    monkeypatch.setattr("src.connectors.mcp.oauth._post_token", fake_post_token)

    await exchange_code_for_tokens(provider=_provider(), code="code", code_verifier="verifier")

    assert "resource" not in posted[0]
    assert posted[0]["client_secret"] == "secret-1"


# --- Issuer discovery -------------------------------------------------------------------------


def _fake_issuer_metadata(monkeypatch: pytest.MonkeyPatch, registrations: list[str]) -> None:
    async def fake_fetch_json(url: str) -> dict[str, Any]:
        assert url.startswith("https://issuer.example/.well-known/")
        return {
            "authorization_endpoint": "https://issuer.example/authorize",
            "token_endpoint": "https://issuer.example/token",
            "registration_endpoint": "https://issuer.example/register",
            "scopes_supported": ["openid", "everything"],
        }

    async def fake_register_client(endpoint: str, scope: str, **_: Any) -> dict[str, Any]:
        registrations.append(endpoint)
        return {"client_id": "dcr-client", "client_secret": "dcr-secret"}

    monkeypatch.setattr("src.connectors.mcp.oauth._fetch_json", fake_fetch_json)
    monkeypatch.setattr("src.connectors.mcp.oauth._register_client", fake_register_client)


@pytest.mark.asyncio
async def test_issuer_discovery_registers_a_client(monkeypatch: pytest.MonkeyPatch) -> None:
    registrations: list[str] = []
    _fake_issuer_metadata(monkeypatch, registrations)

    discovered = await discover_authorization_server("https://issuer.example")

    assert registrations == ["https://issuer.example/register"]
    assert discovered.client_id == "dcr-client"
    assert discovered.client_registration == "dynamic"
    assert discovered.resource_url == ""
    # The server's scopes_supported is everything it can issue, not what a connector should request.
    assert discovered.scope == ""


@pytest.mark.asyncio
async def test_issuer_discovery_can_skip_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    registrations: list[str] = []
    _fake_issuer_metadata(monkeypatch, registrations)

    discovered = await discover_authorization_server("https://issuer.example", register_client=False)

    assert registrations == []
    assert discovered.client_id == ""
    assert discovered.client_registration == "manual"


def test_discovery_request_needs_exactly_one_source() -> None:
    assert MCPOAuthDiscoveryRequest.model_validate({"issuer_url": "https://issuer.example"}).server_url is None
    with pytest.raises(ValidationError):
        MCPOAuthDiscoveryRequest.model_validate({})
    with pytest.raises(ValidationError):
        MCPOAuthDiscoveryRequest.model_validate(
            {"server_url": "https://mcp.example", "issuer_url": "https://issuer.example"}
        )


# --- Auth type none ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_without_auth_sends_no_credentials() -> None:
    client = FakeOAuthMCPClient()
    service, _repository = _service(client)
    created = service.create_connection(
        OWNER,
        MCPConnectionCreateRequest.model_validate(
            {"name": "Public MCP", "server_url": "https://public.example/mcp", "auth_type": "none"}
        ),
    )
    service.enable_for_agent(owner_email=OWNER, agent_id="agent-1", mcp_id=created.mcp_id)

    listed = await service.list_runtime_tools(owner_email=OWNER, agent_id="agent-1", caller=OWNER_CALLER)

    assert created.auth_type == MCPAuthType.NONE
    assert listed["connectors"][0]["tools"][0]["name"] == "search_pages"
    assert client.auth_headers == [{}]


# --- Tools pagination -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tools_follows_next_cursor() -> None:
    cursors: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        if payload["method"] == "initialize":
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": payload["id"], "result": {"protocolVersion": "2025-06-18"}}
            )
        if payload["method"] == "notifications/initialized":
            return httpx.Response(202)
        cursor = payload["params"].get("cursor")
        cursors.append(cursor)
        pages = {None: ({"name": "a"}, "page-2"), "page-2": ({"name": "b"}, None)}
        tool, next_cursor = pages[cursor]
        result: dict[str, Any] = {"tools": [tool]}
        if next_cursor:
            result["nextCursor"] = next_cursor
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result})

    connection = MCPConnection(
        owner_email=OWNER, name="Atlassian", server_url="https://mcp.example/mcp", encrypted_auth_config="unused"
    )

    result = await StreamableHTTPMCPClient(transport=httpx.MockTransport(handler)).list_tools(connection, {})

    assert result == {"tools": [{"name": "a"}, {"name": "b"}]}
    assert cursors == [None, "page-2"]
