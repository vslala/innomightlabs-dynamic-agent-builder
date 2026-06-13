"""MCP runtime tool specs."""

from __future__ import annotations

from src.agents.tool_runtime.commands import (
    ToolCommandCategory,
    ToolCommandMetadata,
    ToolIdempotency,
    ToolSpec,
)
from src.connectors.mcp.runtime_tools import MCP_CALL_TOOL, MCP_LIST_TOOLS


MCP_TOOL_SPECS = [
    ToolSpec(
        MCP_LIST_TOOLS,
        ToolCommandMetadata(
            category=ToolCommandCategory.MCP,
            idempotency=ToolIdempotency.READ_ONLY,
            allow_parallel=True,
        ),
    ),
    ToolSpec(
        MCP_CALL_TOOL,
        ToolCommandMetadata(
            category=ToolCommandCategory.MCP,
            idempotency=ToolIdempotency.NON_IDEMPOTENT_WRITE,
        ),
    ),
]
