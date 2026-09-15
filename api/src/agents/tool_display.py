"""Derives the tool name/args a conversation UI should display for a tool call.

Wrapper tools (e.g. `call_mcp_tool`) carry the real tool identity nested inside
their arguments. `derive_display_tool` unwraps that so the SSE stream can carry
a display-friendly name/args alongside the raw wrapper values needed for audit.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

DisplayTool = tuple[str, Optional[dict[str, Any]]]
_Resolver = Callable[[str, Optional[dict[str, Any]]], Optional[DisplayTool]]


def _resolve_call_mcp_tool(tool_name: str, tool_args: Optional[dict[str, Any]]) -> Optional[DisplayTool]:
    if tool_name != "call_mcp_tool" or not tool_args:
        return None
    mcp_tool_name = tool_args.get("tool_name")
    if not isinstance(mcp_tool_name, str) or not mcp_tool_name.strip():
        return None
    arguments = tool_args.get("arguments")
    return mcp_tool_name.strip(), arguments if isinstance(arguments, dict) else None


#: Ordered strategies for unwrapping a wrapper tool's real name/args. The first
#: resolver that returns a match wins; none matching falls back to the raw call.
_RESOLVERS: list[_Resolver] = [_resolve_call_mcp_tool]


def derive_display_tool(tool_name: str, tool_args: Optional[dict[str, Any]]) -> DisplayTool:
    """Return the (name, args) a user-facing activity view should show."""
    for resolve in _RESOLVERS:
        resolved = resolve(tool_name, tool_args)
        if resolved is not None:
            return resolved
    return tool_name, tool_args
