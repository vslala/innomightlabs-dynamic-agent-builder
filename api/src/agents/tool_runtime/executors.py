"""Executor adapters for agent tool families."""

from __future__ import annotations

import json
from typing import Any, Protocol

from src.agents.runtime_state import AgentTurnState


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
    async def execute(self, tool_name: str, tool_input: dict[str, Any], agent_id: str) -> str:
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


class NativeToolExecutorAdapter:
    def __init__(self, native_tools: NativeToolExecutor):
        self._native_tools = native_tools

    async def execute(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        state: AgentTurnState,
    ) -> str:
        return await self._native_tools.execute(tool_name, tool_input, state.agent_id)


class SkillToolExecutor:
    def __init__(self, skill_runtime: SkillRuntime):
        self._skill_runtime = skill_runtime

    async def execute(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        state: AgentTurnState,
    ) -> str:
        return await self._skill_runtime.handle_tool_call(
            tool_name=tool_name,
            tool_input=tool_input,
            agent_id=state.agent_id,
            owner_email=state.owner_email,
            actor_email=state.actor_email,
            actor_id=state.actor_id,
            conversation_id=state.conversation_id,
            user_message_id=state.user_message_id,
        )


class MCPToolExecutor:
    def __init__(self, mcp_runtime: MCPRuntime | None):
        self._mcp_runtime = mcp_runtime

    async def execute(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        state: AgentTurnState,
    ) -> str:
        if not self._mcp_runtime:
            raise ValueError("MCP runtime is not configured")

        if tool_name == "list_mcp_tools":
            raw_mcp_id = tool_input.get("mcp_id")
            mcp_id = str(raw_mcp_id).strip() if raw_mcp_id is not None else None
            result = await self._mcp_runtime.list_runtime_tools(
                owner_email=state.owner_email,
                agent_id=state.agent_id,
                mcp_id=mcp_id or None,
            )
            return _json_result(result)

        if tool_name == "call_mcp_tool":
            mcp_id = str(tool_input.get("mcp_id", "")).strip()
            mcp_tool_name = str(tool_input.get("tool_name", "")).strip()
            arguments = tool_input.get("arguments", {})
            if not mcp_id or not mcp_tool_name:
                raise ValueError("Missing required arguments: mcp_id and tool_name")
            if not isinstance(arguments, dict):
                raise ValueError("'arguments' must be an object")

            result = await self._mcp_runtime.call_runtime_tool(
                owner_email=state.owner_email,
                agent_id=state.agent_id,
                mcp_id=mcp_id,
                tool_name=mcp_tool_name,
                arguments=arguments,
            )
            return _json_result(result)

        raise ValueError(f"Unknown MCP runtime tool: {tool_name}")


def _json_result(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True)
