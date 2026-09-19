"""MCP runtime tool specs."""

from __future__ import annotations

from src.agents.tool_runtime.mcp_contracts import CallMCPToolInput, ListMCPToolsInput
from src.agents.tool_runtime.specs import ToolCategory, ToolSpec
from src.connectors.mcp.runtime_tools import MCP_CALL_TOOL, MCP_LIST_TOOLS

MCP_LIST_TOOLS_SPEC = ToolSpec(
    definition=MCP_LIST_TOOLS,
    category=ToolCategory.MCP,
    input_model=ListMCPToolsInput,
)

MCP_CALL_TOOL_SPEC = ToolSpec(
    definition=MCP_CALL_TOOL,
    category=ToolCategory.MCP,
    input_model=CallMCPToolInput,
)

MCP_TOOL_SPECS = [MCP_LIST_TOOLS_SPEC, MCP_CALL_TOOL_SPEC]
