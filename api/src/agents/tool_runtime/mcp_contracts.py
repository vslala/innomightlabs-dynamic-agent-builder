"""Input contracts for built-in MCP runtime tools."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ListMCPToolsInput(BaseModel):
    mcp_id: str | None = None


class CallMCPToolInput(BaseModel):
    mcp_id: str
    tool_name: str
    arguments: dict[str, Any]
