from __future__ import annotations

MCP_LIST_TOOLS = {
    "name": "list_mcp_tools",
    "description": (
        "List the tools of enabled MCP connectors. A small connector shows every tool with its input schema; a "
        "large one shows a tool_index of names and summaries, so call again with its mcp_id and tools=[...] for "
        "the schemas you will use, or query='...' to search."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mcp_id": {
                "type": "string",
                "description": "MCP connector id. Omit to list every enabled MCP connector.",
            },
            "tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Exact tool names, from a tool_index, whose input schemas you need.",
            },
            "query": {
                "type": "string",
                "description": "Words describing the tool you need; returns the best matches with their schemas.",
            },
        },
        "required": [],
    },
}

MCP_CALL_TOOL = {
    "name": "call_mcp_tool",
    "description": (
        "Call a tool on an enabled MCP connector, with the exact tool name and the argument shape of its input "
        "schema (from list_mcp_tools, or the loaded tools in your instructions)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mcp_id": {
                "type": "string",
                "description": "MCP connector id that owns the tool.",
            },
            "tool_name": {
                "type": "string",
                "description": "Exact MCP tool name, from list_mcp_tools or the loaded tools.",
            },
            "arguments": {
                "type": "object",
                "description": "Arguments matching the MCP tool input schema.",
            },
        },
        "required": ["mcp_id", "tool_name", "arguments"],
    },
}

MCP_RUNTIME_TOOLS = [MCP_LIST_TOOLS, MCP_CALL_TOOL]
MCP_RUNTIME_TOOL_NAMES = {tool["name"] for tool in MCP_RUNTIME_TOOLS}
