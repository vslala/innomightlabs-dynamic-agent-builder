"""Binding the declared tool specs to the runtimes that serve them."""

from __future__ import annotations

from functools import partial

from src.agents.tool_runtime.handlers import (
    MCPRuntime,
    NativeToolExecutor,
    SkillRuntime,
    call_mcp_tool,
    list_mcp_tools,
    run_native_tool,
    run_skill_tool,
)
from src.agents.tool_runtime.mcp import MCP_CALL_TOOL_SPEC, MCP_LIST_TOOLS_SPEC
from src.agents.tool_runtime.registry import ToolRegistry
from src.agents.tool_runtime.skills import SKILL_TOOL_SPECS
from src.agents.tool_runtime.specs import BoundTool, ToolHandler, ToolSpec
from src.tools.native.specs import NATIVE_TOOL_SPECS


def build_default_tool_registry(
    *,
    skill_runtime: SkillRuntime,
    native_tools: NativeToolExecutor,
    mcp_runtime: MCPRuntime | None = None,
) -> ToolRegistry:
    native: ToolHandler = partial(run_native_tool, native_tools)
    skill: ToolHandler = partial(run_skill_tool, skill_runtime)

    return ToolRegistry(
        [
            *_bind(NATIVE_TOOL_SPECS, native),
            *_bind(SKILL_TOOL_SPECS, skill),
            BoundTool(MCP_LIST_TOOLS_SPEC, partial(list_mcp_tools, mcp_runtime)),
            BoundTool(MCP_CALL_TOOL_SPEC, partial(call_mcp_tool, mcp_runtime)),
        ]
    )


def _bind(specs: list[ToolSpec], handler: ToolHandler) -> list[BoundTool]:
    return [BoundTool(spec, handler) for spec in specs]
