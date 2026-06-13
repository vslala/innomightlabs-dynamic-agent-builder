from __future__ import annotations

import json
from typing import Any

from src.agents.runtime_state import AgentTurnState
from src.agents.tool_execution import ToolExecutionRouter


class FakeSkillRuntime:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    async def handle_tool_call(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, Any],
        agent_id: str,
        owner_email: str,
        actor_email: str,
        actor_id: str,
        conversation_id: str,
        user_message_id: str | None = None,
    ) -> str:
        self.calls.append(
            {
                "tool_name": tool_name,
                "tool_input": tool_input,
                "agent_id": agent_id,
                "owner_email": owner_email,
                "actor_email": actor_email,
                "actor_id": actor_id,
                "conversation_id": conversation_id,
                "user_message_id": user_message_id,
            }
        )
        return "skill result"


class FakeNativeTools:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    async def execute(self, tool_name: str, tool_input: dict[str, Any], agent_id: str) -> str:
        self.calls.append(
            {
                "tool_name": tool_name,
                "tool_input": tool_input,
                "agent_id": agent_id,
            }
        )
        return "native result"


class FakeMCPRuntime:
    def __init__(self):
        self.list_calls: list[dict[str, Any]] = []
        self.call_calls: list[dict[str, Any]] = []

    async def list_runtime_tools(
        self,
        *,
        owner_email: str,
        agent_id: str,
        mcp_id: str | None = None,
    ) -> dict[str, Any]:
        self.list_calls.append(
            {
                "owner_email": owner_email,
                "agent_id": agent_id,
                "mcp_id": mcp_id,
            }
        )
        return {"connectors": []}

    async def call_runtime_tool(
        self,
        *,
        owner_email: str,
        agent_id: str,
        mcp_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        self.call_calls.append(
            {
                "owner_email": owner_email,
                "agent_id": agent_id,
                "mcp_id": mcp_id,
                "tool_name": tool_name,
                "arguments": arguments,
            }
        )
        return {"content": [{"text": "mcp result"}]}


def _state() -> AgentTurnState:
    return AgentTurnState(
        owner_email="owner@example.com",
        actor_email="actor@example.com",
        actor_id="actor-1",
        conversation_id="conversation-1",
        agent_id="agent-1",
        provider_name="OpenAI",
        model_name="gpt-5.5",
        user_message="hello",
        user_message_id="message-1",
    )


async def test_router_delegates_skill_tools_through_command_adapter():
    skill_runtime = FakeSkillRuntime()
    router = ToolExecutionRouter(
        skill_runtime=skill_runtime,
        native_tools=FakeNativeTools(),
        mcp_runtime=FakeMCPRuntime(),
    )

    outcome = await router.execute(
        tool_name="execute_skill_action",
        tool_input={"skill_id": "demo", "action": "run", "arguments": {"x": 1}},
        tool_use_id="tool-1",
        state=_state(),
    )

    assert outcome.success is True
    assert outcome.result == "skill result"
    assert skill_runtime.calls == [
        {
            "tool_name": "execute_skill_action",
            "tool_input": {"skill_id": "demo", "action": "run", "arguments": {"x": 1}},
            "agent_id": "agent-1",
            "owner_email": "owner@example.com",
            "actor_email": "actor@example.com",
            "actor_id": "actor-1",
            "conversation_id": "conversation-1",
            "user_message_id": "message-1",
        }
    ]


async def test_router_marks_prompt_dirty_from_command_metadata_for_memory_writes():
    native_tools = FakeNativeTools()
    state = _state()
    router = ToolExecutionRouter(
        skill_runtime=FakeSkillRuntime(),
        native_tools=native_tools,
        mcp_runtime=FakeMCPRuntime(),
    )

    outcome = await router.execute(
        tool_name="core_memory_append",
        tool_input={"block": "human", "content": "Likes concise answers."},
        tool_use_id="tool-1",
        state=state,
    )

    assert outcome.success is True
    assert state.prompt_dirty is True
    assert native_tools.calls == [
        {
            "tool_name": "core_memory_append",
            "tool_input": {"block": "human", "content": "Likes concise answers."},
            "agent_id": "agent-1",
        }
    ]


async def test_router_does_not_mark_prompt_dirty_for_native_reads():
    state = _state()
    router = ToolExecutionRouter(
        skill_runtime=FakeSkillRuntime(),
        native_tools=FakeNativeTools(),
        mcp_runtime=FakeMCPRuntime(),
    )

    outcome = await router.execute(
        tool_name="core_memory_read",
        tool_input={"block": "human"},
        tool_use_id="tool-1",
        state=state,
    )

    assert outcome.success is True
    assert state.prompt_dirty is False


async def test_router_delegates_mcp_tools_through_command_adapter():
    mcp_runtime = FakeMCPRuntime()
    router = ToolExecutionRouter(
        skill_runtime=FakeSkillRuntime(),
        native_tools=FakeNativeTools(),
        mcp_runtime=mcp_runtime,
    )

    outcome = await router.execute(
        tool_name="call_mcp_tool",
        tool_input={
            "mcp_id": "mcp-1",
            "tool_name": "site_audit",
            "arguments": {"url": "https://example.com"},
        },
        tool_use_id="tool-1",
        state=_state(),
    )

    assert outcome.success is True
    assert json.loads(outcome.result)["content"][0]["text"] == "mcp result"
    assert mcp_runtime.call_calls == [
        {
            "owner_email": "owner@example.com",
            "agent_id": "agent-1",
            "mcp_id": "mcp-1",
            "tool_name": "site_audit",
            "arguments": {"url": "https://example.com"},
        }
    ]


async def test_router_preserves_recoverable_error_outcome_for_unknown_tools():
    router = ToolExecutionRouter(
        skill_runtime=FakeSkillRuntime(),
        native_tools=FakeNativeTools(),
        mcp_runtime=FakeMCPRuntime(),
    )

    outcome = await router.execute(
        tool_name="missing_tool",
        tool_input={},
        tool_use_id="tool-1",
        state=_state(),
    )

    assert outcome.success is False
    assert outcome.result == "Error: Unknown tool: missing_tool"
