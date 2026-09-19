"""Running a tool against the runtime that serves its family."""

from __future__ import annotations

import json
from typing import Any, Protocol

from src.agents.runtime_state import AgentTurnState
from src.agents.tool_runtime.contexts import (
    MCPToolContext,
    NativeToolContext,
    SkillToolContext,
)


class SkillRuntime(Protocol):
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
        ...


class NativeToolExecutor(Protocol):
    async def execute(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: NativeToolContext,
    ) -> str:
        ...


class MCPRuntime(Protocol):
    async def list_runtime_tools(
        self,
        *,
        owner_email: str,
        agent_id: str,
        mcp_id: str | None = None,
    ) -> dict[str, Any]:
        ...

    async def call_runtime_tool(
        self,
        *,
        owner_email: str,
        agent_id: str,
        mcp_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        ...


async def run_native_tool(
    native_tools: NativeToolExecutor,
    tool_name: str,
    tool_input: dict[str, Any],
    state: AgentTurnState,
) -> str:
    return await native_tools.execute(
        tool_name, tool_input, NativeToolContext.of(state)
    )


async def run_skill_tool(
    skill_runtime: SkillRuntime,
    tool_name: str,
    tool_input: dict[str, Any],
    state: AgentTurnState,
) -> str:
    context = SkillToolContext.of(state)
    return await skill_runtime.handle_tool_call(
        tool_name=tool_name,
        tool_input=tool_input,
        agent_id=context.agent_id,
        owner_email=context.owner_email,
        actor_email=context.actor_email,
        actor_id=context.actor_id,
        conversation_id=context.conversation_id,
        user_message_id=context.user_message_id,
    )


async def list_mcp_tools(
    mcp_runtime: MCPRuntime | None,
    tool_name: str,
    tool_input: dict[str, Any],
    state: AgentTurnState,
) -> str:
    del tool_name
    context = MCPToolContext.of(state)
    result = await _required(mcp_runtime).list_runtime_tools(
        owner_email=context.owner_email,
        agent_id=context.agent_id,
        mcp_id=tool_input.get("mcp_id") or None,
    )
    return _json_result(result)


async def call_mcp_tool(
    mcp_runtime: MCPRuntime | None,
    tool_name: str,
    tool_input: dict[str, Any],
    state: AgentTurnState,
) -> str:
    del tool_name
    context = MCPToolContext.of(state)
    # mcp_id, tool_name and arguments are all required by CallMCPToolInput,
    # which has already validated this input.
    result = await _required(mcp_runtime).call_runtime_tool(
        owner_email=context.owner_email,
        agent_id=context.agent_id,
        mcp_id=tool_input["mcp_id"],
        tool_name=tool_input["tool_name"],
        arguments=tool_input["arguments"],
    )
    return _json_result(result)


def _required(mcp_runtime: MCPRuntime | None) -> MCPRuntime:
    if not mcp_runtime:
        raise ValueError("MCP runtime is not configured")
    return mcp_runtime


def _json_result(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True)
