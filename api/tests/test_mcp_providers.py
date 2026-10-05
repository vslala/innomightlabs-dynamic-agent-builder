from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from src.connectors.mcp.models import (
    MCPAuthType,
    MCPConnection,
    MCPConnectionUpdateRequest,
    MCPOAuthDiscoveryResponse,
    MCPProviderInstallRequest,
    MCPTransport,
)
from src.connectors.mcp.providers import PROVIDERS, get_provider
from src.connectors.mcp.providers.base import ProviderInstall
from src.connectors.mcp.providers.resolver import ProviderInstallSecrets
from src.connectors.mcp.resolved import HttpTarget, StdioTarget
from src.connectors.mcp.service import MCPConnectorService
from src.form_models import FormInputType
from tests.test_mcp_connectors import (
    OWNER_CALLER,
    FakeMCPUsage,
    FakeAgentRepository,
    FakeMCPRepository,
    FakeOAuthMCPClient,
    make_agent,
)

OWNER = "owner@example.com"
RETURN_TO = "http://localhost:5173/dashboard/connectors"

GITHUB_INPUTS = {"oauth_client_id": "gh-client", "oauth_client_secret": "gh-secret"}


def _service() -> tuple[MCPConnectorService, FakeMCPRepository, FakeOAuthMCPClient]:
    repository = FakeMCPRepository()
    client = FakeOAuthMCPClient()
    service = MCPConnectorService(
        repository=repository,  # type: ignore[arg-type]
        agent_repository=FakeAgentRepository(make_agent()),  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
        usage=FakeMCPUsage(),  # type: ignore[arg-type]
    )
    return service, repository, client


def _sample_inputs(key: str) -> dict[str, str]:
    provider = get_provider(key)
    return {field.name: field.value or f"{field.name}-value" for field in provider.inputs if not field.is_optional}


def _fake_discovery(monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, Any]], *, registered: bool) -> None:
    async def fake_discover(server_url: str, *, register_client: bool = True) -> MCPOAuthDiscoveryResponse:
        calls.append({"server_url": server_url, "register_client": register_client})
        return MCPOAuthDiscoveryResponse(
            authorization_url="https://auth.example/authorize",
            token_url="https://auth.example/token",
            client_id="dcr-client" if registered else "",
            client_secret="dcr-secret" if registered else "",
            scope="read:jira",
            resource_url=server_url.rstrip("/"),
            authorization_server="https://auth.example",
            registered_client=registered,
            client_registration="dynamic" if registered else "manual",
        )

    monkeypatch.setattr("src.connectors.mcp.service.discover_oauth_provider", fake_discover)


async def _complete_sign_in(
    service: MCPConnectorService,
    monkeypatch: pytest.MonkeyPatch,
    mcp_id: str,
    tokens: dict[str, Any],
) -> None:
    async def fake_exchange(**_: Any) -> dict[str, Any]:
        return tokens

    monkeypatch.setattr("src.connectors.mcp.service.exchange_code_for_tokens", fake_exchange)
    await service.complete_oauth(owner_email=OWNER, mcp_id=mcp_id, code="code", code_verifier="verifier")


# --- Preset contract --------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(PROVIDERS))
def test_preset_target_matches_its_declared_transport(key: str) -> None:
    provider = get_provider(key)

    target = provider.target(ProviderInstall(inputs=_sample_inputs(key)))

    expected = StdioTarget if provider.transport == MCPTransport.STDIO else HttpTarget
    assert isinstance(target, expected)


@pytest.mark.parametrize("key", sorted(PROVIDERS))
def test_preset_oauth_client_secrets_are_password_inputs(key: str) -> None:
    provider = get_provider(key)

    for field in provider.inputs:
        if "secret" in field.name or "token" in field.name:
            assert field.input_type == FormInputType.PASSWORD, field.name


def test_unknown_provider_is_not_found() -> None:
    with pytest.raises(ValueError, match="not found"):
        get_provider("nope")


# --- GitHub (fixed OAuth with the user's own OAuth App) ----------------------------------------


def test_github_is_read_only_unless_writes_are_allowed() -> None:
    github = get_provider("github")

    read_only = github.target(ProviderInstall(inputs=GITHUB_INPUTS))
    writable = github.target(ProviderInstall(inputs={**GITHUB_INPUTS, "allow_writes": "yes"}))

    assert isinstance(read_only, HttpTarget) and isinstance(writable, HttpTarget)
    assert read_only.headers["X-MCP-Readonly"] == "true"
    assert writable.headers["X-MCP-Readonly"] == "false"
    assert "X-MCP-Toolsets" not in read_only.headers


def test_github_normalizes_toolsets() -> None:
    target = get_provider("github").target(ProviderInstall(inputs={**GITHUB_INPUTS, "toolsets": " repos, issues ,"}))

    assert isinstance(target, HttpTarget)
    assert target.headers["X-MCP-Toolsets"] == "repos,issues"


@pytest.mark.asyncio
async def test_github_install_signs_in_with_the_users_client(monkeypatch: pytest.MonkeyPatch) -> None:
    service, repository, client = _service()

    installed = await service.install_provider(
        OWNER, "github", MCPProviderInstallRequest(inputs=GITHUB_INPUTS, return_to=RETURN_TO)
    )

    assert installed.connection.provider_key == "github"
    assert installed.connection.setup_state == "needs_sign_in"
    assert installed.connection.auth_type == MCPAuthType.OAUTH
    assert installed.authorize_url is not None
    authorize = urlparse(installed.authorize_url)
    query = parse_qs(authorize.query)
    assert f"{authorize.scheme}://{authorize.netloc}{authorize.path}" == "https://github.com/login/oauth/authorize"
    assert query["client_id"] == ["gh-client"]
    assert query["scope"] == ["repo read:org read:user"]
    assert "resource" not in query

    # GitHub OAuth App tokens have no expiry and no refresh token.
    await _complete_sign_in(service, monkeypatch, installed.connection.mcp_id, {"access_token": "gho_1"})
    assert service.get_connection(OWNER, installed.connection.mcp_id).setup_state == "ready"

    service.enable_for_agent(owner_email=OWNER, agent_id="agent-1", mcp_id=installed.connection.mcp_id)
    listed = await service.list_runtime_tools(owner_email=OWNER, agent_id="agent-1", caller=OWNER_CALLER)

    assert "error" not in listed["connectors"][0]
    assert client.auth_headers == [{"X-MCP-Readonly": "true", "Authorization": "Bearer gho_1"}]
    stored = repository.find_connection(OWNER, installed.connection.mcp_id)
    assert stored is not None and stored.server_url == ""


# --- Atlassian (discovered OAuth with dynamic registration) -----------------------------------


@pytest.mark.asyncio
async def test_atlassian_installs_in_one_click_with_dcr(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    _fake_discovery(monkeypatch, calls, registered=True)
    service, _repository, client = _service()

    installed = await service.install_provider(OWNER, "atlassian", MCPProviderInstallRequest(return_to=RETURN_TO))

    assert calls == [{"server_url": "https://mcp.atlassian.com/v2/mcp", "register_client": True}]
    assert installed.authorize_url is not None
    query = parse_qs(urlparse(installed.authorize_url).query)
    assert query["client_id"] == ["dcr-client"]
    assert query["resource"] == ["https://mcp.atlassian.com/v2/mcp"]

    await _complete_sign_in(
        service,
        monkeypatch,
        installed.connection.mcp_id,
        {"access_token": "atl-token", "refresh_token": "atl-refresh", "expires_in": 3600},
    )
    service.enable_for_agent(owner_email=OWNER, agent_id="agent-1", mcp_id=installed.connection.mcp_id)
    await service.list_runtime_tools(owner_email=OWNER, agent_id="agent-1", caller=OWNER_CALLER)

    assert client.auth_headers == [{"Authorization": "Bearer atl-token"}]


@pytest.mark.asyncio
async def test_atlassian_install_fails_when_registration_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_discovery(monkeypatch, [], registered=False)
    service, repository, _client = _service()

    with pytest.raises(ValueError, match="did not register"):
        await service.install_provider(OWNER, "atlassian", MCPProviderInstallRequest(return_to=RETURN_TO))

    assert repository.connections == {}


# --- Canva (discovered endpoints, the user's own client) --------------------------------------


@pytest.mark.asyncio
async def test_canva_discovers_endpoints_but_uses_the_users_client(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    _fake_discovery(monkeypatch, calls, registered=False)
    service, _repository, _client = _service()

    installed = await service.install_provider(
        OWNER,
        "canva",
        MCPProviderInstallRequest(
            inputs={"oauth_client_id": "canva-client", "oauth_client_secret": "canva-secret"},
            return_to=RETURN_TO,
        ),
    )

    assert calls == [{"server_url": "https://mcp.canva.com/mcp", "register_client": False}]
    assert installed.authorize_url is not None
    assert parse_qs(urlparse(installed.authorize_url).query)["client_id"] == ["canva-client"]


# --- Install validation -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_install_rejects_unknown_missing_and_invalid_inputs() -> None:
    service, repository, _client = _service()

    with pytest.raises(ValueError, match="Unknown"):
        await service.install_provider(
            OWNER, "github", MCPProviderInstallRequest(inputs={**GITHUB_INPUTS, "bogus": "1"}, return_to=RETURN_TO)
        )
    with pytest.raises(ValueError, match="needs"):
        await service.install_provider(
            OWNER, "github", MCPProviderInstallRequest(inputs={"oauth_client_id": "x"}, return_to=RETURN_TO)
        )
    with pytest.raises(ValueError, match="must be one of"):
        await service.install_provider(
            OWNER,
            "github",
            MCPProviderInstallRequest(inputs={**GITHUB_INPUTS, "allow_writes": "maybe"}, return_to=RETURN_TO),
        )

    assert repository.connections == {}


# --- Secrets, settings, and updates -----------------------------------------------------------


@pytest.mark.asyncio
async def test_secret_inputs_are_never_returned() -> None:
    service, _repository, _client = _service()
    installed = await service.install_provider(
        OWNER, "github", MCPProviderInstallRequest(inputs={**GITHUB_INPUTS, "toolsets": "repos"}, return_to=RETURN_TO)
    )
    mcp_id = installed.connection.mcp_id

    form = service.connection_settings_form(OWNER, mcp_id)
    values = {field.name: field.value for field in form.form_inputs}

    assert installed.connection.inputs == {"oauth_client_id": "gh-client", "toolsets": "repos"}
    assert values["oauth_client_id"] == "gh-client"
    assert values["oauth_client_secret"] is None
    assert form.submit_path == f"/connectors/mcp/{mcp_id}"


@pytest.mark.asyncio
async def test_settings_update_keeps_blank_secrets() -> None:
    service, repository, _client = _service()
    installed = await service.install_provider(
        OWNER, "github", MCPProviderInstallRequest(inputs=GITHUB_INPUTS, return_to=RETURN_TO)
    )
    mcp_id = installed.connection.mcp_id

    await service.update_connection(
        OWNER,
        mcp_id,
        MCPConnectionUpdateRequest(
            inputs={"oauth_client_id": "gh-client-2", "oauth_client_secret": "", "allow_writes": "yes"}
        ),
    )

    stored = repository.find_connection(OWNER, mcp_id)
    assert stored is not None
    assert ProviderInstallSecrets.of(stored).inputs == {
        "oauth_client_id": "gh-client-2",
        "oauth_client_secret": "gh-secret",
        "allow_writes": "yes",
    }


@pytest.mark.asyncio
async def test_catalog_installs_reject_connection_config_changes() -> None:
    service, _repository, _client = _service()
    installed = await service.install_provider(
        OWNER, "github", MCPProviderInstallRequest(inputs=GITHUB_INPUTS, return_to=RETURN_TO)
    )

    with pytest.raises(ValueError, match="configured by their provider"):
        await service.update_connection(
            OWNER,
            installed.connection.mcp_id,
            MCPConnectionUpdateRequest.model_validate({"server_url": "https://evil.example/mcp"}),
        )


@pytest.mark.asyncio
async def test_custom_connections_reject_inputs() -> None:
    service, repository, _client = _service()
    connection = repository.save_connection(
        MCPConnection(owner_email=OWNER, name="Custom", server_url="https://mcp.example", encrypted_auth_config="x")
    )

    with pytest.raises(ValueError, match="catalog connectors"):
        await service.update_connection(OWNER, connection.mcp_id, MCPConnectionUpdateRequest(inputs={"a": "b"}))


@pytest.mark.asyncio
async def test_setup_state_reports_missing_required_inputs() -> None:
    service, repository, _client = _service()
    installed = await service.install_provider(
        OWNER, "github", MCPProviderInstallRequest(inputs=GITHUB_INPUTS, return_to=RETURN_TO)
    )
    # Simulates a preset gaining a required input after this install was saved.
    stored = repository.find_connection(OWNER, installed.connection.mcp_id)
    assert stored is not None
    stored.encrypted_auth_config = ProviderInstallSecrets(inputs={"oauth_client_id": "gh-client"}).encrypted()

    assert service.get_connection(OWNER, installed.connection.mcp_id).setup_state == "needs_input"


@pytest.mark.asyncio
async def test_provider_listing_counts_installs() -> None:
    service, _repository, _client = _service()
    await service.install_provider(OWNER, "github", MCPProviderInstallRequest(inputs=GITHUB_INPUTS, return_to=RETURN_TO))

    listed = {provider.key: provider for provider in service.list_providers(OWNER)}

    assert listed["github"].installed_count == 1
    assert listed["github"].has_sign_in is True
    assert listed["atlassian"].has_inputs is False
    assert listed["atlassian"].installed_count == 0


def test_rows_without_provider_key_stay_custom() -> None:
    item = MCPConnection(
        owner_email=OWNER, name="Custom", server_url="https://mcp.example", encrypted_auth_config="x"
    ).to_dynamo_item()
    item.pop("provider_key")

    assert MCPConnection.from_dynamo_item(item).provider_key is None


# --- Routes -----------------------------------------------------------------------------------


def test_catalog_routes_are_not_shadowed_by_connection_ids(test_client: Any, auth_headers: dict[str, str]) -> None:
    from main import app
    from src.connectors.mcp.service import get_mcp_connector_service

    service, _repository, _client = _service()
    app.dependency_overrides[get_mcp_connector_service] = lambda: service
    try:
        providers = test_client.get("/connectors/mcp/providers", headers=auth_headers)
        form = test_client.get("/connectors/mcp/providers/github/forms/install", headers=auth_headers)
        missing = test_client.get("/connectors/mcp/providers/nope/forms/install", headers=auth_headers)
        installed = test_client.post(
            "/connectors/mcp/providers/github/install",
            json={"inputs": GITHUB_INPUTS, "return_to": RETURN_TO},
            headers=auth_headers,
        )
        invalid = test_client.post(
            "/connectors/mcp/providers/github/install",
            json={"inputs": {}, "return_to": RETURN_TO},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_mcp_connector_service, None)

    assert providers.status_code == 200
    assert {item["key"] for item in providers.json()} == set(PROVIDERS)
    assert form.status_code == 200
    assert form.json()["submit_path"] == "/connectors/mcp/providers/github/install"
    assert missing.status_code == 404
    assert installed.status_code == 201
    assert installed.json()["authorize_url"].startswith("https://github.com/login/oauth/authorize")
    assert "gh-secret" not in installed.text
    assert invalid.status_code == 400
