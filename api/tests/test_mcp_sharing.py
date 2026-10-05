"""Sharing an owner's MCP connector with widget visitors, A2A agents and API keys."""

from __future__ import annotations

from typing import Any

import pytest
from boto3.dynamodb.conditions import Key
from pydantic import ValidationError

from src.agents.architectures.krishna_memgpt_prompt import build_krishna_memgpt_system_prompt
from src.connectors.mcp.client import MCPClientError
from src.connectors.mcp.disclaimer import DISCLAIMER_VERSION
from src.connectors.mcp.models import (
    AgentMCPConnection,
    MCPCaller,
    MCPCatalogTool,
    MCPConnection,
    MCPSharingUpdateRequest,
)
from src.connectors.mcp.service import MCPConnectorService
from src.connectors.mcp.usage import MCPCall, MCPUsageRepository
from src.skills.models import ActorKind
from tests.test_mcp_connectors import (
    OWNER_CALLER,
    FakeAgentRepository,
    FakeMCPRepository,
    FakeMCPUsage,
    create_connection,
    make_agent,
)

OWNER = "owner@example.com"
VISITOR = MCPCaller(actor_kind=ActorKind.VISITOR, actor_id="visitor-1", actor_email="v@example.com")
A2A = MCPCaller(actor_kind=ActorKind.A2A, actor_id="a2a:key-1")

SEARCH = {"name": "search", "description": "Search issues", "annotations": {"readOnlyHint": True}}
CREATE = {"name": "create_issue", "description": "File an issue", "annotations": {"destructiveHint": False}}
DELETE = {"name": "delete_issue", "description": "Delete an issue"}


class JiraLikeClient:
    """A server offering one read, one write and one destructive tool."""

    def __init__(self, *, reachable: bool = True, result: dict[str, Any] | None = None):
        self.reachable = reachable
        self.result = result or {"content": [{"type": "text", "text": "done"}]}
        self.tool_calls: list[str] = []

    async def list_tools(self, connection: MCPConnection, auth_headers: dict[str, str]) -> dict[str, Any]:
        if not self.reachable:
            raise MCPClientError("connection refused")
        return {"tools": [SEARCH, CREATE, DELETE]}

    async def call_tool(
        self, connection: MCPConnection, auth_headers: dict[str, str], *, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        if not self.reachable:
            raise MCPClientError("connection refused")
        self.tool_calls.append(tool_name)
        return self.result


def _service(client: JiraLikeClient | None = None) -> tuple[MCPConnectorService, FakeMCPRepository, FakeMCPUsage]:
    repository, usage = FakeMCPRepository(), FakeMCPUsage()
    service = MCPConnectorService(
        repository=repository,  # type: ignore[arg-type]
        agent_repository=FakeAgentRepository(make_agent()),  # type: ignore[arg-type]
        client=client or JiraLikeClient(),  # type: ignore[arg-type]
        usage=usage,  # type: ignore[arg-type]
    )
    return service, repository, usage


async def _enabled_connector(service: MCPConnectorService) -> str:
    mcp_id = create_connection(service)
    service.enable_for_agent(owner_email=OWNER, agent_id="agent-1", mcp_id=mcp_id)
    await service.capture_tool_catalog(OWNER, mcp_id)
    return mcp_id


def _share(service: MCPConnectorService, mcp_id: str, kinds: list[ActorKind], tools: list[str]):
    return service.share(
        owner_email=OWNER,
        agent_id="agent-1",
        mcp_id=mcp_id,
        request=MCPSharingUpdateRequest(
            available_to=kinds, allowed_tools=tools, accept_disclaimer_version=DISCLAIMER_VERSION
        ),
    )


def _tool_names(listed: dict[str, Any]) -> list[str]:
    return [tool["name"] for connector in listed["connectors"] for tool in connector["tools"]]


# The tool catalog


def test_catalog_tools_are_grouped_by_what_the_server_says_they_do():
    search, create, delete = (MCPCatalogTool.from_server(tool) for tool in (SEARCH, CREATE, DELETE))

    assert (search.read_only, search.destructive) == (True, False)
    assert (create.read_only, create.destructive) == (False, False)
    # Without annotations the MCP spec presumes the worst, and so do we.
    assert (delete.read_only, delete.destructive) == (False, True)


def test_catalog_descriptions_are_kept_short():
    tool = MCPCatalogTool.from_server({"name": "long", "description": "x" * 5000})

    assert len(tool.description) == 400


async def test_enabling_a_connector_snapshots_its_tools():
    service, repository, _ = _service()

    mcp_id = await _enabled_connector(service)

    catalog = repository.find_tool_catalog(OWNER, mcp_id)
    assert catalog is not None
    assert catalog.tool_names() == {"search", "create_issue", "delete_issue"}


async def test_an_unreachable_server_does_not_fail_the_snapshot():
    service, repository, _ = _service(JiraLikeClient(reachable=False))

    mcp_id = await _enabled_connector(service)

    assert repository.find_tool_catalog(OWNER, mcp_id) is None


async def test_the_share_dialog_lists_tools_live_for_connectors_without_a_snapshot():
    service, repository, _ = _service()
    mcp_id = create_connection(service)
    service.enable_for_agent(owner_email=OWNER, agent_id="agent-1", mcp_id=mcp_id)

    view = await service.sharing_view(owner_email=OWNER, agent_id="agent-1", mcp_id=mcp_id)

    assert view.catalog is not None
    assert [tool.name for tool in view.catalog.tools] == ["search", "create_issue", "delete_issue"]
    assert repository.find_tool_catalog(OWNER, mcp_id) is not None
    assert view.disclaimer.version == DISCLAIMER_VERSION
    assert "Ahrefs" in view.disclaimer.paragraphs[0]


async def test_the_share_dialog_explains_when_the_tools_cannot_be_listed():
    service, _, _ = _service(JiraLikeClient(reachable=False))
    mcp_id = create_connection(service)
    service.enable_for_agent(owner_email=OWNER, agent_id="agent-1", mcp_id=mcp_id)

    view = await service.sharing_view(owner_email=OWNER, agent_id="agent-1", mcp_id=mcp_id)

    assert view.catalog is None
    assert view.catalog_error and "Ahrefs" in view.catalog_error


# Choosing what to share


async def test_sharing_records_the_owners_consent():
    service, repository, _ = _service()
    mcp_id = await _enabled_connector(service)

    view = _share(service, mcp_id, [ActorKind.VISITOR], ["search", "search"])

    assert view.sharing.available_to == [ActorKind.VISITOR]
    assert view.sharing.allowed_tools == ["search"]
    consent = repository.find_agent_connection("agent-1", mcp_id).sharing.consent
    assert consent.accepted_by == OWNER
    assert consent.version == DISCLAIMER_VERSION


@pytest.mark.parametrize(
    ("request_fields", "refusal"),
    [
        ({"allowed_tools": ["search"], "accept_disclaimer_version": None}, "Accept the current sharing disclaimer"),
        ({"allowed_tools": ["search"], "accept_disclaimer_version": "2020-01-01"}, "Accept the current sharing"),
        ({"allowed_tools": [], "accept_disclaimer_version": DISCLAIMER_VERSION}, "Choose at least one tool"),
        ({"allowed_tools": ["drop_db"], "accept_disclaimer_version": DISCLAIMER_VERSION}, "drop_db"),
    ],
)
async def test_sharing_is_refused_unless_it_is_informed_and_specific(request_fields, refusal):
    service, repository, _ = _service()
    mcp_id = await _enabled_connector(service)

    with pytest.raises(ValueError, match=refusal):
        service.share(
            owner_email=OWNER,
            agent_id="agent-1",
            mcp_id=mcp_id,
            request=MCPSharingUpdateRequest(available_to=[ActorKind.VISITOR], **request_fields),
        )
    assert repository.find_agent_connection("agent-1", mcp_id).sharing.available_to == []


def test_the_owner_is_not_someone_to_share_with():
    with pytest.raises(ValidationError, match="owner always has every connector"):
        MCPSharingUpdateRequest(available_to=[ActorKind.OWNER], allowed_tools=["search"])


async def test_stopping_sharing_needs_no_consent_and_forgets_everything():
    service, repository, _ = _service()
    mcp_id = await _enabled_connector(service)
    _share(service, mcp_id, [ActorKind.VISITOR], ["search"])

    service.share(
        owner_email=OWNER, agent_id="agent-1", mcp_id=mcp_id, request=MCPSharingUpdateRequest(available_to=[])
    )

    sharing = repository.find_agent_connection("agent-1", mcp_id).sharing
    assert (sharing.available_to, sharing.allowed_tools, sharing.consent) == ([], [], None)


async def test_re_enabling_a_connector_keeps_what_was_shared():
    service, repository, _ = _service()
    mcp_id = await _enabled_connector(service)
    _share(service, mcp_id, [ActorKind.VISITOR], ["search"])

    service.enable_for_agent(owner_email=OWNER, agent_id="agent-1", mcp_id=mcp_id, enabled=True)

    assert repository.find_agent_connection("agent-1", mcp_id).sharing.allowed_tools == ["search"]


def test_links_saved_before_sharing_existed_stay_owner_only():
    link = AgentMCPConnection(agent_id="agent-1", owner_email=OWNER, mcp_id="m")
    legacy_item = {key: value for key, value in link.to_dynamo_item().items() if key != "sharing"}

    loaded = AgentMCPConnection.from_dynamo_item(legacy_item)

    assert loaded.usable_by(ActorKind.OWNER)
    assert not any(loaded.usable_by(kind) for kind in (ActorKind.VISITOR, ActorKind.A2A, ActorKind.API))


# What outsiders get at runtime


async def test_an_unshared_connector_does_not_exist_for_outsiders():
    service, _, usage = _service()
    mcp_id = await _enabled_connector(service)

    connections = service.list_agent_connections(
        owner_email=OWNER, agent_id="agent-1", actor_kind=ActorKind.VISITOR, verify_agent=False
    )
    listed = await service.list_runtime_tools(owner_email=OWNER, agent_id="agent-1", caller=VISITOR)

    assert connections == []
    assert listed == {"connectors": []}
    with pytest.raises(ValueError, match="is not enabled for this agent"):
        await service.call_runtime_tool(
            owner_email=OWNER, agent_id="agent-1", caller=VISITOR, mcp_id=mcp_id, tool_name="search", arguments={}
        )
    assert usage.calls == []


async def test_outsiders_see_and_call_only_the_shared_tools():
    client = JiraLikeClient()
    service, _, usage = _service(client)
    mcp_id = await _enabled_connector(service)
    _share(service, mcp_id, [ActorKind.VISITOR], ["search", "create_issue"])

    listed = await service.list_runtime_tools(owner_email=OWNER, agent_id="agent-1", caller=VISITOR)
    await service.call_runtime_tool(
        owner_email=OWNER, agent_id="agent-1", caller=VISITOR, mcp_id=mcp_id, tool_name="search", arguments={}
    )
    # Refused with the same words as a missing connector, so the visitor learns nothing about it.
    with pytest.raises(ValueError, match=f"MCP connector '{mcp_id}' is not enabled for this agent"):
        await service.call_runtime_tool(
            owner_email=OWNER, agent_id="agent-1", caller=VISITOR, mcp_id=mcp_id, tool_name="delete_issue", arguments={}
        )

    assert _tool_names(listed) == ["search", "create_issue"]
    assert client.tool_calls == ["search"]
    assert [call.tool_name for call in usage.calls] == ["search"]


async def test_each_audience_is_shared_with_on_its_own():
    service, _, _ = _service()
    mcp_id = await _enabled_connector(service)
    _share(service, mcp_id, [ActorKind.VISITOR], ["search"])

    listed = await service.list_runtime_tools(owner_email=OWNER, agent_id="agent-1", caller=A2A)

    assert listed == {"connectors": []}


async def test_the_owner_keeps_every_tool_whatever_is_shared():
    service, _, _ = _service()
    mcp_id = await _enabled_connector(service)
    _share(service, mcp_id, [ActorKind.VISITOR], ["search"])

    listed = await service.list_runtime_tools(owner_email=OWNER, agent_id="agent-1", caller=OWNER_CALLER)

    assert _tool_names(listed) == ["search", "create_issue", "delete_issue"]


def test_outsiders_are_told_the_connectors_belong_to_someone_else():
    connection = type("Connection", (), {"mcp_id": "m", "name": "Jira"})()

    shared = build_krishna_memgpt_system_prompt(
        agent_persona="Persona", enabled_mcp_connections=[connection], mcp_shared_by_owner=True
    )
    owned = build_krishna_memgpt_system_prompt(agent_persona="Persona", enabled_mcp_connections=[connection])

    assert "run with the agent owner's account" in shared
    assert "run with the agent owner's account" not in owned


# Recording every call


async def test_a_call_is_recorded_with_who_asked_and_how_it_went():
    service, _, usage = _service()
    mcp_id = await _enabled_connector(service)
    _share(service, mcp_id, [ActorKind.VISITOR], ["create_issue"])

    await service.call_runtime_tool(
        owner_email=OWNER,
        agent_id="agent-1",
        caller=VISITOR,
        mcp_id=mcp_id,
        tool_name="create_issue",
        arguments={"summary": "Love the site"},
    )

    [call] = usage.calls
    assert (call.actor_kind, call.actor_id, call.actor_email) == (ActorKind.VISITOR, "visitor-1", "v@example.com")
    assert (call.connection_name, call.tool_name, call.success, call.error) == ("Ahrefs", "create_issue", True, None)
    assert call.arguments_preview == '{"summary": "Love the site"}'


async def test_a_tool_that_reports_an_error_is_recorded_as_failed():
    failing = JiraLikeClient(result={"isError": True, "content": [{"type": "text", "text": "Project not found"}]})
    service, _, usage = _service(failing)
    mcp_id = await _enabled_connector(service)

    await service.call_runtime_tool(
        owner_email=OWNER, agent_id="agent-1", caller=OWNER_CALLER, mcp_id=mcp_id, tool_name="search", arguments={}
    )

    [call] = usage.calls
    assert (call.success, call.error) == (False, "Project not found")


async def test_an_unreachable_server_is_recorded_as_failed():
    client = JiraLikeClient()
    service, _, usage = _service(client)
    mcp_id = await _enabled_connector(service)
    client.reachable = False

    with pytest.raises(MCPClientError):
        await service.call_runtime_tool(
            owner_email=OWNER, agent_id="agent-1", caller=OWNER_CALLER, mcp_id=mcp_id, tool_name="search", arguments={}
        )

    [call] = usage.calls
    assert (call.success, call.error) == (False, "connection refused")


async def test_recording_trouble_never_fails_the_tool_call():
    service, _, usage = _service()
    mcp_id = await _enabled_connector(service)

    def broken(call: MCPCall) -> None:
        raise RuntimeError("DynamoDB is down")

    usage.record = broken  # type: ignore[method-assign]

    result = await service.call_runtime_tool(
        owner_email=OWNER, agent_id="agent-1", caller=OWNER_CALLER, mcp_id=mcp_id, tool_name="search", arguments={}
    )

    assert result["content"][0]["text"] == "done"


def test_calls_are_kept_as_an_expiring_audit_row_and_a_daily_count(dynamodb_table):
    repository = MCPUsageRepository()
    call = MCPCall(
        agent_id="agent-1",
        mcp_id="m",
        connection_name="Jira",
        tool_name="search",
        actor_kind=ActorKind.VISITOR,
        actor_id="visitor-1",
        success=True,
        duration_ms=120,
    )

    repository.record(call)
    repository.record(call.model_copy(update={"call_id": "second", "success": False, "duration_ms": 80}))

    calls = dynamodb_table.query(KeyConditionExpression=Key("pk").eq("Agent#agent-1#MCPCalls"))["Items"]
    assert len(calls) == 2
    assert int(calls[0]["ttl"]) - call.called_at.timestamp() == pytest.approx(90 * 24 * 3600, abs=1)
    [daily] = dynamodb_table.query(KeyConditionExpression=Key("pk").eq("Agent#agent-1#MCPUsage"))["Items"]
    assert daily["sk"] == f"Day#{call.day}#visitor#m#search"
    assert (daily["calls"], daily["errors"], daily["duration_ms_total"]) == (2, 1, 200)
