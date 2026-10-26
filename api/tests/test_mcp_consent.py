"""MCP tools that ask the owner first: the default from the catalog, the owner's choice, and who may call them.

See docs/LLD-action-consent.md ("MCP tools: per-tool consent").
"""

from __future__ import annotations

import json

import pytest

from src.agents.runtime_state import AgentTurnState
from src.consent.gate import ConsentGate, McpTools
from src.consent.models import ConsentScope, StandingConsent, mcp_key
from src.consent.repository import ConsentRepository
from src.skills.models import ActorKind
from src.skills.registry import ConsentMissingError
from tests.mock_data import account_for, user_id_for
from tests.test_mcp_connectors import OWNER_CALLER, create_connection
from tests.test_mcp_sharing import OWNER, VISITOR, _enabled_connector, _service, _share, _tool_names


def _state(actor_kind: ActorKind = ActorKind.OWNER) -> AgentTurnState:
    return AgentTurnState(
        owner_email=OWNER, actor_email=OWNER, actor_id=OWNER, actor_kind=actor_kind, conversation_id="conversation-1",
        agent_id="agent-1", model_name="m", user_message="x", account_id=account_for(OWNER), owner_id=user_id_for(OWNER),
        consent_scope=ConsentScope.interactive(),
    )


async def _call(service, mcp_id: str, tool: str, *, caller=OWNER_CALLER, grant: str | None = None):
    return await service.call_runtime_tool(
        account_id=account_for(OWNER), agent_id="agent-1", caller=caller, mcp_id=mcp_id, tool_name=tool, arguments={},
        consent_grant=grant,
    )


async def test_by_default_the_tools_the_server_marks_destructive_ask_first():
    service, _, _ = _service()
    mcp_id = await _enabled_connector(service)

    policy, _ = service.tool_policy(account_for(OWNER), mcp_id)
    assert not policy.chosen and policy.consent_required_tools == ["delete_issue"]

    with pytest.raises(ConsentMissingError):
        await _call(service, mcp_id, "delete_issue")
    await _call(service, mcp_id, "delete_issue", grant="consent:consent_1")
    await _call(service, mcp_id, "search")


async def test_a_connection_whose_tools_were_never_listed_asks_about_none_of_them():
    service, _, _ = _service()
    mcp_id = create_connection(service)
    policy, catalog = service.tool_policy(account_for(OWNER), mcp_id)
    assert catalog is None and policy.consent_required_tools == []


async def test_the_owner_is_shown_a_card_for_a_tool_that_asks(dynamodb_table):
    service, _, _ = _service()
    mcp_id = await _enabled_connector(service)
    gate = ConsentGate([McpTools(service)])

    asks = await gate.check(tool_name="call_mcp_tool", tool_use_id="t1", state=_state(),
                            tool_input={"mcp_id": mcp_id, "tool_name": "delete_issue", "arguments": {"id": "J-1"}})
    card = json.loads(asks.result)["consent"]
    assert card["key"] == mcp_key(mcp_id, "delete_issue") and card["editable"] == []
    assert any(block["kind"] == "code" for block in card["blocks"])

    runs = await gate.check(tool_name="call_mcp_tool", tool_use_id="t2", state=_state(),
                            tool_input={"mcp_id": mcp_id, "tool_name": "search", "arguments": {}})
    assert runs.result is None and runs.grant is None


async def test_a_tool_shared_before_keeps_working_for_outsiders_until_the_owner_chooses_to_be_asked(dynamodb_table):
    service, _, _ = _service()
    mcp_id = await _enabled_connector(service)
    _share(service, mcp_id, [ActorKind.VISITOR], ["search", "delete_issue"])

    # Sharing it was the owner's choice; a default doesn't take it back
    listed = await service.list_runtime_tools(account_id=account_for(OWNER), agent_id="agent-1", caller=VISITOR)
    assert sorted(_tool_names(listed)) == ["delete_issue", "search"]
    await _call(service, mcp_id, "delete_issue", caller=VISITOR)

    service.set_tool_policy(account_for(OWNER), mcp_id, ["delete_issue"], by="owner")
    listed = await service.list_runtime_tools(account_id=account_for(OWNER), agent_id="agent-1", caller=VISITOR)
    assert _tool_names(listed) == ["search"]
    with pytest.raises(ValueError, match="not enabled"):
        await _call(service, mcp_id, "delete_issue", caller=VISITOR)
    refused = await ConsentGate([McpTools(service)]).check(
        tool_name="call_mcp_tool", tool_use_id="t", state=_state(ActorKind.VISITOR),
        tool_input={"mcp_id": mcp_id, "tool_name": "delete_issue", "arguments": {}},
    )
    assert json.loads(refused.result)["consent"] == "refused"


async def test_the_owner_chooses_only_from_the_listed_tools():
    service, _, _ = _service()
    mcp_id = await _enabled_connector(service)
    with pytest.raises(ValueError, match="not offered"):
        service.set_tool_policy(account_for(OWNER), mcp_id, ["drop_database"], by="owner")
    chosen = service.set_tool_policy(account_for(OWNER), mcp_id, ["create_issue"], by="owner")
    assert chosen.chosen and chosen.consent_required_tools == ["create_issue"]


async def test_an_agents_asking_tools_can_be_always_allowed_until_the_connection_is_unlinked(dynamodb_table):
    service, _, _ = _service()
    mcp_id = await _enabled_connector(service)
    key = mcp_key(mcp_id, "delete_issue")
    [(found_key, title, _)] = service.consent_tools(account_id=account_for(OWNER), agent_id="agent-1")
    assert (found_key, title) == (key, "delete_issue")

    consents = ConsentRepository()
    consents.save_standing(StandingConsent(agent_id="agent-1", key=key, title=title, granted_by="owner"))
    service.disable_for_agent(account_id=account_for(OWNER), agent_id="agent-1", mcp_id=mcp_id)
    assert consents.list_standing("agent-1") == []
