from __future__ import annotations

MCP_LIST_TOOLS = {
    "name": "list_mcp_tools",
    "description": (
        "List tools exposed by enabled MCP connectors. Use this before calling "
        "an MCP tool when you need to inspect available tool names and schemas."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mcp_id": {
                "type": "string",
                "description": "Optional MCP connector id. Omit to list tools for all enabled MCP connectors.",
            }
        },
        "required": [],
    },
}

MCP_CALL_TOOL = {
    "name": "call_mcp_tool",
    "description": (
        "Call a tool on an enabled MCP connector. Use the exact tool name and "
        "argument shape returned by list_mcp_tools."
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
                "description": "Exact MCP tool name returned by list_mcp_tools.",
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
