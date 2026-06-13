"""Tool execution routing for agent architectures.

The public router contract remains stable for the agentic loop, while concrete
tool behavior is isolated behind command objects registered by tool name.
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.runtime_state import AgentTurnState
from src.agents.tool_runtime import (
    ToolCommandRegistry,
    ToolCommandRequest,
    ToolExecutionOutcome,
    build_default_tool_command_registry,
)
from src.agents.tool_runtime.executors import MCPRuntime, NativeToolExecutor, SkillRuntime

log = logging.getLogger(__name__)


class ToolExecutionRouter:
    """Execute tool calls through registered tool commands."""

    def __init__(
        self,
        *,
        skill_runtime: SkillRuntime,
        native_tools: NativeToolExecutor,
        mcp_runtime: MCPRuntime | None = None,
        registry: ToolCommandRegistry | None = None,
    ):
        self._registry = registry or build_default_tool_command_registry(
            skill_runtime=skill_runtime,
            native_tools=native_tools,
            mcp_runtime=mcp_runtime,
        )

    async def execute(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
        state: AgentTurnState,
    ) -> ToolExecutionOutcome:
        try:
            command = self._registry.get(tool_name)
            outcome = await command.execute(
                ToolCommandRequest(
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_use_id=tool_use_id,
                    state=state,
                )
            )
            if command.metadata.mutates_prompt_context:
                state.prompt_dirty = True
            return outcome

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


__all__ = ["ToolExecutionOutcome", "ToolExecutionRouter"]
