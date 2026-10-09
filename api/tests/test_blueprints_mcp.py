"""MCP connections in blueprints: found on the account, linked to agents, and connected by the person, not Ada."""

import json

import pytest
import yaml
from fastapi import BackgroundTasks

from src.agents.tool_results import interpret_tool_result
from src.blueprints.catalog import example_yaml
from src.blueprints.executor import apply_blueprint
from src.blueprints.export import export_agent
from src.blueprints.issues import BlueprintInvalid
from src.blueprints.kinds import mcp_connection as mcp_kind
from src.blueprints.planner import plan_blueprint
from src.blueprints.validator import validate_blueprint
from src.builder import connections
from src.builder.tools import BuilderTools
from src.config import settings
from src.connectors.mcp.models import MCPConnection
from src.connectors.mcp.repository import get_mcp_connection_repository
from src.llm.events import SSEEventType
from tests.mock_data import TEST_USER_EMAIL
from tests.test_builder_ada import account, session, turn_state  # noqa: F401

TEAM = example_yaml("web-research-team") or ""


@pytest.fixture
def ready(monkeypatch) -> set[str]:
    """Connections that count as signed in. Signing in is a real OAuth flow, so tests decide it here."""
    signed_in: set[str] = set()
    check = lambda connection: connection.mcp_id in signed_in  # noqa: E731
    monkeypatch.setattr(mcp_kind, "is_ready", check)
    monkeypatch.setattr(connections, "is_ready", check)
    monkeypatch.setattr(settings, "is_superuser_email", lambda email: True)
    return signed_in


def tavily(signed_in: set[str] | None = None) -> MCPConnection:
    connection = get_mcp_connection_repository().save_connection(MCPConnection(
        owner_email=TEST_USER_EMAIL, name="Tavily", server_url="", encrypted_auth_config="", provider_key="tavily",
    ))
    if signed_in is not None:
        signed_in.add(connection.mcp_id)
    return connection


def plan_for(text: str):
    validated = validate_blueprint(text, {})
    return validated, plan_blueprint(validated, TEST_USER_EMAIL)


def build(text: str):
    validated, plan = plan_for(text)
    assert plan.ok, plan.blockers
    return plan, apply_blueprint(validated, plan, TEST_USER_EMAIL, BackgroundTasks())


def linked(agent_id: str) -> set[str]:
    return {link.mcp_id for link in get_mcp_connection_repository().list_agent_connections(agent_id)}


# --- The spec ----------------------------------------------------------------------------------


def test_the_providers_come_from_the_preset_catalog():
    text = TEAM.replace("provider: tavily", "provider: tavilly")
    with pytest.raises(BlueprintInvalid) as raised:
        validate_blueprint(text, {})
    assert any(issue.path == "resources.web_search.provider" for issue in raised.value.issues)


@pytest.mark.parametrize(
    "change, message",
    [
        ("    provider: tavily\n", "Say which MCP server to connect."),
        ("    provider: tavily\n    id: m-1\n    remove: true\n", "can't delete this MCP connection"),
    ],
)
def test_a_connection_needs_a_provider_and_cant_be_deleted(change, message):
    text = TEAM.replace("    provider: tavily\n", change if "remove" in change else "")
    with pytest.raises(BlueprintInvalid) as raised:
        validate_blueprint(text, {})
    assert any(message in issue.message for issue in raised.value.issues)


# --- Plan and apply ----------------------------------------------------------------------------


def test_an_unconnected_provider_blocks_the_plan(account, ready):  # noqa: F811
    _, plan = plan_for(TEAM)
    assert [issue.path for issue in plan.blockers] == ["resources.web_search.provider"]


def test_the_researcher_gets_the_connected_tools_once(account, ready):  # noqa: F811
    connection = tavily(ready)
    plan, built = build(TEAM)
    step = next(step for step in plan.steps if step.resource == "web_search")
    assert (step.action, step.existing_id) == ("unchanged", connection.mcp_id)
    assert linked(built.resources["researcher"].id) == {connection.mcp_id}
    assert linked(built.resources["lead"].id) == set()

    again, _ = build(TEAM)
    assert not again.changes_anything


def test_an_exported_agent_keeps_its_connection(account, ready):  # noqa: F811
    connection = tavily(ready)
    _, built = build(TEAM)
    exported = yaml.safe_load(export_agent(built.resources["researcher"].id, TEST_USER_EMAIL) or "")
    assert exported["resources"]["tools"] == {
        "kind": "McpConnection", "id": connection.mcp_id, "provider": "tavily", "name": "Tavily",
    }
    assert exported["resources"]["agent"]["mcp_connections"] == ["tools"]
    _, plan = plan_for(yaml.safe_dump(exported, sort_keys=False))
    assert plan.ok and not plan.changes_anything


def test_taking_the_tools_away(account, ready):  # noqa: F811
    connection = tavily(ready)
    _, built = build(TEAM)
    researcher = built.resources["researcher"].id
    exported = yaml.safe_load(export_agent(researcher, TEST_USER_EMAIL) or "")
    exported["resources"]["agent"]["mcp_connections"] = []
    exported["resources"]["agent"]["remove_mcp_connections"] = ["tools"]

    plan, applied = build(yaml.safe_dump(exported, sort_keys=False))
    assert plan.removals == ["take the Tavily tools away"]
    assert linked(researcher) == set()
    assert get_mcp_connection_repository().find_connection(TEST_USER_EMAIL, connection.mcp_id)  # the account keeps it


# --- The system asks the person to connect -----------------------------------------------------


async def test_planning_without_the_account_connected_shows_a_connect_card(session, ready):  # noqa: F811
    result = json.loads(await BuilderTools().plan("plan_blueprint", {"yaml": TEAM, "params": {}}, turn_state(session)))
    assert result["type"] == "connect_request" and "plan_id" not in result
    assert result["connect"]["provider"] == "tavily" and result["connect"]["title"] == "Connect Tavily"
    [interpreted] = interpret_tool_result(json.dumps(result))
    assert interpreted.event.event_type == SSEEventType.CONNECT_REQUEST
    assert interpreted.event.connect["conversation_id"] == session.conversation_id

    # Once connected, the same call plans.
    tavily(ready)
    result = json.loads(await BuilderTools().plan("plan_blueprint", {}, turn_state(session)))
    assert result["ok"] is True and result["plan_id"]


class FakeService:
    def __init__(self):
        self.installed: list[str] = []
        self.started: list[str] = []

    async def install_provider(self, owner_email, key, request):
        self.installed.append(key)
        assert request.return_to.endswith(connections.POPUP_RETURN_PATH)
        return type("Installed", (), {"authorize_url": f"https://auth.example/{key}"})()

    def start_oauth(self, *, owner_email, mcp_id, return_to):
        self.started.append(mcp_id)
        return f"https://auth.example/again/{mcp_id}"


async def test_connecting_installs_once_then_signs_in_again(account, ready):  # noqa: F811
    service = FakeService()
    assert await connections.start_connection(service, TEST_USER_EMAIL, "tavily") == "https://auth.example/tavily"

    pending = tavily()  # installed but not signed in yet
    assert await connections.start_connection(service, TEST_USER_EMAIL, "tavily") == f"https://auth.example/again/{pending.mcp_id}"
    ready.add(pending.mcp_id)
    assert await connections.start_connection(service, TEST_USER_EMAIL, "tavily") is None
    assert service.installed == ["tavily"]


async def test_a_preset_needing_set_up_isnt_connected_from_the_chat(account, ready):  # noqa: F811
    with pytest.raises(ValueError, match="Connectors page"):
        await connections.start_connection(FakeService(), TEST_USER_EMAIL, "github")
    assert connections.missing_connections(TEAM.replace("provider: tavily", "provider: github"), TEST_USER_EMAIL) == []


def test_the_connect_route(test_client, auth_headers, session, monkeypatch):  # noqa: F811
    from src.builder import router as builder_router

    async def fake_start(service, user_email, provider):
        return f"https://auth.example/{provider}"

    monkeypatch.setattr(builder_router, "start_connection", fake_start)
    response = test_client.post(
        f"/builder/{session.conversation_id}/connect", json={"provider": "tavily"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json() == {"authorize_url": "https://auth.example/tavily"}
