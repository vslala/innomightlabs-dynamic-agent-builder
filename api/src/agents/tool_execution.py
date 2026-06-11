"""Tool execution routing for agent architectures.

This module centralizes:
- how tool calls are dispatched (native vs skills)
- error handling + logging

Keep behavior identical while we refactor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from src.agents.runtime_state import AgentTurnState
from src.connectors.mcp.runtime_tools import MCP_RUNTIME_TOOL_NAMES

log = logging.getLogger(__name__)


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


@dataclass(frozen=True)
class ToolExecutionOutcome:
    result: str
    success: bool


class ToolExecutionRouter:
    """Route tool calls to skills or native tools."""

    def __init__(
        self,
        *,
        skill_runtime: SkillRuntime,
        native_tools: NativeToolExecutor,
        mcp_runtime: MCPRuntime | None = None,
    ):
        self._skill_runtime = skill_runtime
        self._native_tools = native_tools
        self._mcp_runtime = mcp_runtime

    async def execute(self, *, tool_name: str, tool_input: dict[str, Any], tool_use_id: str, state: AgentTurnState) -> ToolExecutionOutcome:
        try:
            if tool_name in {"load_skill", "execute_skill_action"}:
                result = await self._skill_runtime.handle_tool_call(
                    tool_name=tool_name,
                    tool_input=tool_input,
                    agent_id=state.agent_id,
                    owner_email=state.owner_email,
                    actor_email=state.actor_email,
                    actor_id=state.actor_id,
                    conversation_id=state.conversation_id,
                    user_message_id=state.user_message_id,
                )
            elif tool_name in MCP_RUNTIME_TOOL_NAMES:
                result = await self._execute_mcp_tool(tool_name=tool_name, tool_input=tool_input, state=state)
            else:
                result = await self._native_tools.execute(tool_name, tool_input, state.agent_id)

                # Mark prompt dirty when core memory is mutated.
                if tool_name in {"core_memory_append", "core_memory_replace", "core_memory_delete"}:
                    state.prompt_dirty = True

            return ToolExecutionOutcome(result=result, success=True)

        except Exception as e:
            # Preserve legacy behavior for the model/UI while centralizing logs.
            log.error(
                "Tool execution error: tool=%s tool_use_id=%s err=%s",
                tool_name,
                tool_use_id,
                e,
                exc_info=True,
            )
            return ToolExecutionOutcome(result=f"Error: {str(e)}", success=False)

    async def _execute_mcp_tool(
        self,
        *,
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
    import json

    return json.dumps(value, ensure_ascii=True)
