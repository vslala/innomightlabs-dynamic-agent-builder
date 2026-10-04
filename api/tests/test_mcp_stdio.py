from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from pydantic import ValidationError

from src.config import settings
from src.connectors.mcp.client import StreamableHTTPMCPClient
from src.connectors.mcp.models import (
    MCPAuthType,
    MCPConnectionCreateRequest,
    MCPConnectionUpdateRequest,
    MCPProviderInstallRequest,
    MCPTransport,
)
from src.connectors.mcp.providers import PROVIDERS
from src.connectors.mcp.providers.base import ProviderInstall
from src.connectors.mcp.resolved import StdioTarget
from src.connectors.mcp.service import MCPConnectorService
from src.connectors.mcp.sidecar import StdioMCPSidecarClient
from tests.test_mcp_connectors import FakeAgentRepository, FakeMCPRepository, make_agent

OWNER = "owner@example.com"
SIDECAR = "http://sidecar.internal:8080"
RETURN_TO = "http://localhost:5173/dashboard/connectors"
REPO_ROOT = Path(__file__).resolve().parents[2]


class FakeSidecar:
    """The runner's hosted-MCP routes, including a façade that answers like a stdio server would."""

    def __init__(self) -> None:
        self.ensured: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self.facade_methods: list[str] = []
        self.state = "running"
        self.status_response: dict[str, Any] | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer runner-token"
        path = request.url.path
        if path == "/v1/mcp/packages":
            return httpx.Response(200, json=[{"key": "google_ads", "entrypoint": "google-ads-mcp", "installed": True}])
        server_id = path.split("/")[4]
        if path.endswith("/mcp"):
            return self._facade(json.loads(request.content))
        if request.method == "PUT":
            self.ensured.append({"server_id": server_id, **json.loads(request.content)})
            return httpx.Response(200, json=self._status(server_id))
        if request.method == "DELETE":
            self.deleted.append(server_id)
            return httpx.Response(204)
        if self.status_response is None:
            return httpx.Response(404, json={"detail": "MCP server is not running"})
        return httpx.Response(200, json=self.status_response)

    def _status(self, server_id: str) -> dict[str, Any]:
        error = "MCP server exited with code 1" if self.state == "failed" else None
        return {"server_id": server_id, "package": "google_ads", "state": self.state, "error": error}

    def _facade(self, message: dict[str, Any]) -> httpx.Response:
        method = message["method"]
        self.facade_methods.append(method)
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "initialize":
            result: dict[str, Any] = {"protocolVersion": "2025-06-18", "serverInfo": {"name": "Google Ads Server"}}
        elif method == "tools/list":
            result = {"tools": [{"name": "search_search"}]}
        else:
            result = {"content": [{"type": "text", "text": "rows"}]}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": message["id"], "result": result})


@pytest.fixture
def sidecar(monkeypatch: pytest.MonkeyPatch) -> FakeSidecar:
    monkeypatch.setattr(settings, "cli_runner_base_url", SIDECAR)
    monkeypatch.setattr(settings, "cli_runner_shared_token", "runner-token")
    return FakeSidecar()


def _service(sidecar: FakeSidecar) -> tuple[MCPConnectorService, FakeMCPRepository]:
    transport = httpx.MockTransport(sidecar.handler)
    repository = FakeMCPRepository()
    service = MCPConnectorService(
        repository=repository,  # type: ignore[arg-type]
        agent_repository=FakeAgentRepository(make_agent()),  # type: ignore[arg-type]
        client=StreamableHTTPMCPClient(transport=transport),
        sidecar=StdioMCPSidecarClient(transport=transport),
    )
    return service, repository


def _stdio_request(**overrides: Any) -> MCPConnectionCreateRequest:
    return MCPConnectionCreateRequest.model_validate(
        {
            "name": "Hosted",
            "transport": "stdio",
            "stdio": {
                "package": "google_ads",
                "args": ["--verbose"],
                "env": [
                    {"name": "GOOGLE_ADS_DEVELOPER_TOKEN", "value": "dev-token", "secret": True},
                    {"name": "GOOGLE_ADS_LOGIN_CUSTOMER_ID", "value": "123"},
                    {"name": "GOOGLE_APPLICATION_CREDENTIALS", "value": '{"type":"x"}', "kind": "file", "secret": True},
                ],
            },
            **overrides,
        }
    )


OAUTH_PROVIDER = {
    "authorization_url": "https://idp.example/authorize",
    "token_url": "https://idp.example/token",
    "client_id": "user-client",
    "client_secret": "user-secret",
    "scope": "read",
}


async def _sign_in(service: MCPConnectorService, monkeypatch: pytest.MonkeyPatch, mcp_id: str, tokens: dict[str, Any]) -> None:
    async def fake_exchange(**_: Any) -> dict[str, Any]:
        return tokens

    monkeypatch.setattr("src.connectors.mcp.service.exchange_code_for_tokens", fake_exchange)
    await service.complete_oauth(owner_email=OWNER, mcp_id=mcp_id, code="code", code_verifier="verifier")


# --- Create validation ------------------------------------------------------------------------


def test_stdio_auth_type_follows_what_was_supplied() -> None:
    assert _stdio_request().auth_type == MCPAuthType.API_KEY
    public = MCPConnectionCreateRequest.model_validate(
        {"name": "Public", "transport": "stdio", "stdio": {"package": "google_ads"}}
    )
    assert public.auth_type == MCPAuthType.NONE
    oauth = MCPConnectionCreateRequest.model_validate(
        {
            "name": "OAuth",
            "transport": "stdio",
            "stdio": {"package": "google_ads"},
            "oauth": OAUTH_PROVIDER,
            "oauth_delivery": {"kind": "access_token_env", "env_name": "ACCESS_TOKEN"},
        }
    )
    assert oauth.auth_type == MCPAuthType.OAUTH


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"name": "x", "transport": "stdio"}, "stdio is required"),
        (
            {"name": "x", "transport": "stdio", "stdio": {"package": "google_ads"}, "server_url": "https://x.example"},
            "not server_url",
        ),
        (
            {"name": "x", "transport": "stdio", "stdio": {"package": "google_ads", "env": [{"name": "A"}]}},
            "need values",
        ),
        (
            {"name": "x", "transport": "stdio", "stdio": {"package": "google_ads"}, "oauth": OAUTH_PROVIDER},
            "oauth_delivery are required",
        ),
        (
            {
                "name": "x",
                "transport": "stdio",
                "stdio": {"package": "google_ads", "env": [{"name": "ACCESS_TOKEN", "value": "v"}]},
                "oauth": OAUTH_PROVIDER,
                "oauth_delivery": {"kind": "access_token_env", "env_name": "ACCESS_TOKEN"},
            },
            "set by sign-in",
        ),
        (
            {
                "name": "x",
                "transport": "stdio",
                "auth_type": "api_key",
                "stdio": {"package": "google_ads", "env": [{"name": "A", "value": "v"}]},
            },
            "as secret",
        ),
        (
            {
                "name": "x",
                "server_url": "https://x.example",
                "api_key": {"headers": [{"name": "A", "value": "b"}]},
                "stdio": {"package": "google_ads"},
            },
            "only to stdio",
        ),
    ],
)
def test_invalid_stdio_requests_are_rejected(payload: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        MCPConnectionCreateRequest.model_validate(payload)


def test_unknown_oauth_delivery_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MCPConnectionCreateRequest.model_validate(
            {
                "name": "x",
                "transport": "stdio",
                "stdio": {"package": "google_ads"},
                "oauth": OAUTH_PROVIDER,
                "oauth_delivery": {"kind": "bearer_header", "env_name": "X"},
            }
        )


# --- Responses never expose secrets -----------------------------------------------------------


def test_stdio_response_hides_secret_and_file_values(sidecar: FakeSidecar) -> None:
    service, _repository = _service(sidecar)

    created = service.create_connection(OWNER, _stdio_request())

    assert created.transport == MCPTransport.STDIO
    assert created.server_url == ""
    assert created.stdio is not None
    assert [(var.name, var.value) for var in created.stdio.env] == [
        ("GOOGLE_ADS_DEVELOPER_TOKEN", None),
        ("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "123"),
        ("GOOGLE_APPLICATION_CREDENTIALS", None),
    ]
    assert "dev-token" not in created.model_dump_json()


# --- Runtime through the sidecar --------------------------------------------------------------


@pytest.mark.asyncio
async def test_stdio_runtime_ensures_the_server_then_talks_to_the_facade(sidecar: FakeSidecar) -> None:
    service, _repository = _service(sidecar)
    created = service.create_connection(OWNER, _stdio_request())
    service.enable_for_agent(owner_email=OWNER, agent_id="agent-1", mcp_id=created.mcp_id)

    listed = await service.list_runtime_tools(owner_email=OWNER, agent_id="agent-1")
    called = await service.call_runtime_tool(
        owner_email=OWNER, agent_id="agent-1", mcp_id=created.mcp_id, tool_name="search_search", arguments={}
    )

    assert listed["connectors"][0]["tools"] == [{"name": "search_search"}]
    assert called["content"][0]["text"] == "rows"
    assert sidecar.ensured[0] == {
        "server_id": created.mcp_id,
        "spec": {
            "package": "google_ads",
            "args": ["--verbose"],
            "env": {"GOOGLE_ADS_DEVELOPER_TOKEN": "dev-token", "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "123"},
            "files": {"GOOGLE_APPLICATION_CREDENTIALS": '{"type":"x"}'},
        },
        "wait_seconds": 45,
    }
    assert sidecar.facade_methods == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "initialize",
        "notifications/initialized",
        "tools/call",
    ]


@pytest.mark.asyncio
async def test_a_server_that_is_not_running_surfaces_why(sidecar: FakeSidecar) -> None:
    service, _repository = _service(sidecar)
    created = service.create_connection(OWNER, _stdio_request())
    service.enable_for_agent(owner_email=OWNER, agent_id="agent-1", mcp_id=created.mcp_id)

    sidecar.state = "starting"
    starting = await service.list_runtime_tools(owner_email=OWNER, agent_id="agent-1")
    sidecar.state = "failed"
    failed = await service.list_runtime_tools(owner_email=OWNER, agent_id="agent-1")

    assert "still starting" in starting["connectors"][0]["error"]
    assert "exited with code 1" in failed["connectors"][0]["error"]
    assert sidecar.facade_methods == []


@pytest.mark.asyncio
async def test_delete_and_disable_stop_the_hosted_process(sidecar: FakeSidecar) -> None:
    service, _repository = _service(sidecar)
    disabled = service.create_connection(OWNER, _stdio_request())
    deleted = service.create_connection(OWNER, _stdio_request())

    await service.update_connection(OWNER, disabled.mcp_id, MCPConnectionUpdateRequest(enabled=False))
    await service.delete_connection(OWNER, deleted.mcp_id)

    assert sidecar.deleted == [disabled.mcp_id, deleted.mcp_id]


@pytest.mark.asyncio
async def test_remote_connections_never_touch_the_sidecar(sidecar: FakeSidecar) -> None:
    service, _repository = _service(sidecar)
    created = service.create_connection(
        OWNER,
        MCPConnectionCreateRequest.model_validate(
            {"name": "Remote", "server_url": "https://remote.example/mcp", "auth_type": "none"}
        ),
    )

    with pytest.raises(ValueError, match="Only hosted stdio"):
        await service.runtime_status(OWNER, created.mcp_id)
    await service.delete_connection(OWNER, created.mcp_id)

    assert sidecar.deleted == []


@pytest.mark.asyncio
async def test_runtime_status_and_restart(sidecar: FakeSidecar) -> None:
    service, _repository = _service(sidecar)
    created = service.create_connection(OWNER, _stdio_request())

    stopped = await service.runtime_status(OWNER, created.mcp_id)
    sidecar.status_response = {
        "server_id": created.mcp_id,
        "state": "failed",
        "stderr_tail": "boom\nAuthorization: Bearer ya29.secret-token\nbye",
    }
    failed = await service.runtime_status(OWNER, created.mcp_id)
    restarted = await service.restart_runtime(OWNER, created.mcp_id)

    assert stopped.state == "stopped"
    assert failed.stderr_tail == "boom\nAuthorization: Bearer [REDACTED]\nbye"
    assert restarted.state == "running"
    assert sidecar.deleted == [created.mcp_id]
    assert sidecar.ensured[-1]["wait_seconds"] == 0

    await service.update_connection(OWNER, created.mcp_id, MCPConnectionUpdateRequest(enabled=False))
    with pytest.raises(ValueError, match="Enable"):
        await service.restart_runtime(OWNER, created.mcp_id)


# --- Updates ----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_keeps_blank_env_values_by_name(sidecar: FakeSidecar) -> None:
    service, _repository = _service(sidecar)
    created = service.create_connection(OWNER, _stdio_request())

    await service.update_connection(
        OWNER,
        created.mcp_id,
        MCPConnectionUpdateRequest.model_validate(
            {
                "stdio": {
                    "package": "google_ads",
                    "env": [
                        {"name": "GOOGLE_ADS_DEVELOPER_TOKEN", "value": "", "secret": True},
                        {"name": "GOOGLE_ADS_LOGIN_CUSTOMER_ID", "value": "456"},
                    ],
                }
            }
        ),
    )
    service.enable_for_agent(owner_email=OWNER, agent_id="agent-1", mcp_id=created.mcp_id)
    await service.list_runtime_tools(owner_email=OWNER, agent_id="agent-1")

    assert sidecar.ensured[-1]["spec"]["env"] == {
        "GOOGLE_ADS_DEVELOPER_TOKEN": "dev-token",
        "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "456",
    }
    assert sidecar.ensured[-1]["spec"]["files"] == {}


# --- OAuth over stdio -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_access_token_env_delivers_the_token_and_restarts_on_refresh(
    sidecar: FakeSidecar, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _repository = _service(sidecar)
    created = service.create_connection(
        OWNER,
        MCPConnectionCreateRequest.model_validate(
            {
                "name": "Token env",
                "transport": "stdio",
                "stdio": {"package": "google_ads"},
                "oauth": OAUTH_PROVIDER,
                "oauth_delivery": {"kind": "access_token_env", "env_name": "ACCESS_TOKEN"},
            }
        ),
    )
    assert created.oauth_connected is False
    authorize = parse_qs(urlparse(service.start_oauth(owner_email=OWNER, mcp_id=created.mcp_id, return_to=RETURN_TO)).query)
    assert "resource" not in authorize

    await _sign_in(service, monkeypatch, created.mcp_id, {"access_token": "token-1", "refresh_token": "r", "expires_in": 200})
    service.enable_for_agent(owner_email=OWNER, agent_id="agent-1", mcp_id=created.mcp_id)

    async def fake_refresh(**_: Any) -> dict[str, Any]:
        return {"access_token": "token-2", "expires_in": 3600}

    monkeypatch.setattr("src.connectors.mcp.service.refresh_access_token", fake_refresh)
    await service.list_runtime_tools(owner_email=OWNER, agent_id="agent-1")

    # 200s left is inside the 300s buffer of AccessTokenEnv, so the process gets the refreshed token.
    assert sidecar.ensured[-1]["spec"]["env"] == {"ACCESS_TOKEN": "token-2"}
    assert service.get_connection(OWNER, created.mcp_id).oauth_connected is True
    assert service.get_connection(OWNER, created.mcp_id).oauth_delivery is not None


@pytest.mark.asyncio
async def test_google_ads_preset_hands_the_server_an_authorized_user_file(
    sidecar: FakeSidecar, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _repository = _service(sidecar)

    installed = await service.install_provider(
        OWNER,
        "google_ads",
        MCPProviderInstallRequest(
            inputs={
                "oauth_client_id": "gcp-client",
                "oauth_client_secret": "gcp-secret",
                "login_customer_id": "999",
            },
            return_to=RETURN_TO,
        ),
    )
    assert installed.authorize_url is not None
    query = parse_qs(urlparse(installed.authorize_url).query)
    assert query["client_id"] == ["gcp-client"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert "resource" not in query
    assert installed.connection.transport == MCPTransport.STDIO

    await _sign_in(
        service, monkeypatch, installed.connection.mcp_id, {"access_token": "ya29", "refresh_token": "1//r", "expires_in": 3599}
    )
    service.enable_for_agent(owner_email=OWNER, agent_id="agent-1", mcp_id=installed.connection.mcp_id)
    await service.list_runtime_tools(owner_email=OWNER, agent_id="agent-1")

    spec = sidecar.ensured[-1]["spec"]
    assert spec["package"] == "google_ads"
    assert spec["env"] == {"GOOGLE_ADS_LOGIN_CUSTOMER_ID": "999"}
    assert json.loads(spec["files"]["GOOGLE_APPLICATION_CREDENTIALS"]) == {
        "type": "authorized_user",
        "client_id": "gcp-client",
        "client_secret": "gcp-secret",
        "refresh_token": "1//r",
    }


# --- Packages ---------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stdio_packages_come_from_the_sidecar(sidecar: FakeSidecar) -> None:
    service, _repository = _service(sidecar)

    packages = await service.list_stdio_packages()

    assert [package.key for package in packages] == ["google_ads"]


def test_every_stdio_preset_package_is_baked_into_the_sidecar() -> None:
    packages_root = REPO_ROOT / "infra-cli-runner" / "mcp_packages"
    for provider in PROVIDERS.values():
        if provider.transport != MCPTransport.STDIO:
            continue
        sample = {field.name: "x" for field in provider.inputs}
        target = provider.target(ProviderInstall(inputs=sample))
        assert isinstance(target, StdioTarget)
        assert (packages_root / target.package / "package.toml").is_file(), target.package
