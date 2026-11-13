"""`list_mcp_tools` shows a large connector as an index the agent loads tools from, and a turn starts with the tools
the agent used recently already loaded (docs/LLD-agent-context-cost.md, phase 2)."""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from src.agents.architectures.krishna_memgpt_prompt import mcp_section
from src.connectors.mcp.disclosure import INLINE_SCHEMA_CHARS, LOAD_NOTE, ToolRequest, disclose_tools
from src.connectors.mcp.models import MCPCaller
from src.connectors.mcp.usage import RECENT_TOOL_LIMIT, MCPCall, MCPUsageRepository
from src.skills.models import ActorKind
from tests.mock_data import account_for
from tests.test_mcp_connectors import OWNER_CALLER, FakeMCPClient, create_connection, make_service

OWNER = account_for("owner@example.com")


def _tool(name: str, description: str, schema_chars: int = 10) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": {"q": {"type": "string", "description": "x" * schema_chars}}},
    }


#: More than INLINE_SCHEMA_CHARS of schemas, as GitHub's or Notion's connectors have.
LARGE_CONNECTOR = [
    _tool("get_commit", "Get one commit with its diff. Includes the files it changed.", 2_000),
    _tool("list_commits", "List the commits on a branch.", 2_000),
    _tool("create_issue", "Open an issue in a repository.", 2_000),
    _tool("search_code", "Search code across repositories.", 2_000),
    _tool("get_file_contents", "Read a file from a repository.", 2_000),
]
SMALL_CONNECTOR = [_tool("site_audit", "Audit a website.")]


def test_a_small_connector_is_shown_whole_so_it_costs_no_extra_call():
    assert disclose_tools(ToolRequest(tools=SMALL_CONNECTOR)) == {"tools": SMALL_CONNECTOR}


def test_a_large_connector_is_shown_as_an_index_of_names_and_first_sentences():
    disclosed = disclose_tools(ToolRequest(tools=LARGE_CONNECTOR))

    assert "tools" not in disclosed
    assert disclosed["tool_index"][0] == {"name": "get_commit", "summary": "Get one commit with its diff."}
    assert disclosed["note"] == LOAD_NOTE
    assert len(str(disclosed)) < INLINE_SCHEMA_CHARS


def test_the_agent_loads_the_tools_it_names_and_is_told_the_nearest_names_for_the_rest():
    disclosed = disclose_tools(ToolRequest(tools=LARGE_CONNECTOR, names=["get_commit", "get_commits", "get_commit"]))

    assert [tool["name"] for tool in disclosed["tools"]] == ["get_commit"]
    assert disclosed["unknown_tools"] == ["get_commits"]
    assert disclosed["suggestions"][0] == "get_commit"


def test_the_agent_can_search_a_connector_by_what_the_tool_does():
    disclosed = disclose_tools(ToolRequest(tools=LARGE_CONNECTOR, query="open an issue"))

    assert disclosed["tools"][0]["name"] == "create_issue"


class LargeConnectorClient(FakeMCPClient):
    async def list_tools(self, connection, auth_headers):
        await super().list_tools(connection, auth_headers)
        return {"tools": LARGE_CONNECTOR}


def _service_with(client: FakeMCPClient):
    service, repository, _ = make_service()
    service.client = client
    mcp_id = create_connection(service)
    service.enable_for_agent(account_id=OWNER, agent_id="agent-1", mcp_id=mcp_id, enabled=True)
    return service, mcp_id


async def test_the_listing_indexes_a_large_connector_and_loads_named_tools_from_one_server_listing():
    client = LargeConnectorClient()
    service, mcp_id = _service_with(client)

    index = await service.list_runtime_tools(account_id=OWNER, agent_id="agent-1", caller=OWNER_CALLER)
    loaded = await service.list_runtime_tools(
        account_id=OWNER, agent_id="agent-1", caller=OWNER_CALLER, mcp_id=mcp_id, tool_names=["get_commit"]
    )

    assert [entry["name"] for entry in index["connectors"][0]["tool_index"]] == [t["name"] for t in LARGE_CONNECTOR]
    assert loaded["connectors"][0]["tools"] == [LARGE_CONNECTOR[0]]
    # The second listing is served from the cached server list.
    assert client.list_calls == [mcp_id]


class UsedTools:
    def __init__(self, used: list[tuple[str, str]]):
        self.used = used

    def recent_tools(self, agent_id: str) -> list[tuple[str, str]]:
        return self.used


async def test_a_turn_starts_with_the_tools_the_agent_used_recently_that_the_server_still_offers():
    service, mcp_id = _service_with(LargeConnectorClient())
    service.usage = UsedTools([(mcp_id, "list_commits"), (mcp_id, "a_tool_the_server_dropped"), ("gone", "get_commit")])

    recent = await service.recent_runtime_tools(account_id=OWNER, agent_id="agent-1", caller=OWNER_CALLER)

    assert recent == [{"mcp_id": mcp_id, **LARGE_CONNECTOR[1]}]


async def test_a_caller_the_connector_isnt_shared_with_gets_no_recent_tools():
    service, mcp_id = _service_with(LargeConnectorClient())
    service.usage = UsedTools([(mcp_id, "list_commits")])
    visitor = MCPCaller(actor_kind=ActorKind.A2A, actor_id="visitor-1")

    assert await service.recent_runtime_tools(account_id=OWNER, agent_id="agent-1", caller=visitor) == []


def _call(mcp_id: str, tool_name: str, minutes_ago: int, success: bool = True) -> MCPCall:
    return MCPCall(
        agent_id="agent-1",
        mcp_id=mcp_id,
        connection_name="GitHub",
        tool_name=tool_name,
        actor_kind=ActorKind.OWNER,
        actor_id="owner",
        success=success,
        duration_ms=10,
        called_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    )


def test_the_recent_tools_are_the_newest_successful_calls_each_once(dynamodb_table):
    repository = MCPUsageRepository()
    for call in (
        _call("github", "get_commit", minutes_ago=1),
        _call("github", "get_commit", minutes_ago=2),
        _call("notion", "notion-fetch", minutes_ago=3),
        _call("github", "create_issue", minutes_ago=4, success=False),
        _call("github", "list_commits", minutes_ago=5),
    ):
        repository.record(call)

    assert repository.recent_tools("agent-1") == [
        ("github", "get_commit"),
        ("notion", "notion-fetch"),
        ("github", "list_commits"),
    ]


def test_recent_tools_stop_at_the_limit(dynamodb_table):
    repository = MCPUsageRepository()
    for minutes_ago in range(RECENT_TOOL_LIMIT + 3):
        repository.record(_call("github", f"tool_{minutes_ago}", minutes_ago=minutes_ago))

    assert len(repository.recent_tools("agent-1")) == RECENT_TOOL_LIMIT


def test_loaded_tools_are_rendered_with_their_schemas_so_the_agent_calls_them_directly():
    section = mcp_section([], loaded_tools=[{"mcp_id": "github", **LARGE_CONNECTOR[0]}])

    assert "Loaded tools" in section
    assert "- github / get_commit: Get one commit with its diff." in section
    assert '"type": "object"' in section


def test_no_loaded_tools_adds_nothing():
    assert "Loaded tools" not in mcp_section([])


@pytest.mark.parametrize("tool_input, expected", [
    ({}, {"mcp_id": None, "tool_names": None, "query": None}),
    ({"mcp_id": "github", "tools": ["get_commit"]}, {"mcp_id": "github", "tool_names": ["get_commit"], "query": None}),
    ({"query": "commit"}, {"mcp_id": None, "tool_names": None, "query": "commit"}),
])
async def test_the_list_mcp_tools_handler_passes_what_the_agent_asked_for(tool_input, expected):
    from src.agents.tool_runtime.handlers import list_mcp_tools
    from tests.test_agentic_loop import _turn_state

    class Runtime:
        asked: dict[str, Any] = {}

        async def list_runtime_tools(self, **kwargs):
            self.asked = kwargs
            return {"connectors": []}

    runtime = Runtime()
    await list_mcp_tools(runtime, "list_mcp_tools", tool_input, _turn_state())  # type: ignore[arg-type]

    assert {key: runtime.asked[key] for key in expected} == expected
