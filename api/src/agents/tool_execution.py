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

log = logging.getLogger(__name__)


class SkillRuntime(Protocol):
    async def handle_tool_call(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, Any],
        agent_id: str,
        actor_email: str,
        actor_id: str,
        conversation_id: str,
    ) -> str:
        ...


class NativeToolExecutor(Protocol):
    async def execute(self, tool_name: str, tool_input: dict[str, Any], agent_id: str) -> str:
        ...


@dataclass(frozen=True)
class ToolExecutionOutcome:
    result: str
    success: bool


class ToolExecutionRouter:
    """Route tool calls to skills or native tools."""

    def __init__(self, *, skill_runtime: SkillRuntime, native_tools: NativeToolExecutor):
        self._skill_runtime = skill_runtime
        self._native_tools = native_tools

    async def execute(self, *, tool_name: str, tool_input: dict[str, Any], tool_use_id: str, state: AgentTurnState) -> ToolExecutionOutcome:
        try:
            if tool_name in {"load_skill", "execute_skill_action"}:
                result = await self._skill_runtime.handle_tool_call(
                    tool_name=tool_name,
                    tool_input=tool_input,
                    agent_id=state.agent_id,
                    actor_email=state.actor_email,
                    actor_id=state.actor_id,
                    conversation_id=state.conversation_id,
                )
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
