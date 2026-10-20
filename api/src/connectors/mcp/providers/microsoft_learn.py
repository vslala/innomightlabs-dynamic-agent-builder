from __future__ import annotations

from src.connectors.mcp.providers.base import MCPProvider
from src.connectors.mcp.resolved import HttpTarget

MICROSOFT_LEARN_MCP_URL = "https://learn.microsoft.com/api/mcp"


PROVIDER = MCPProvider(
    key="microsoft_learn",
    display_name="Microsoft Learn",
    description="Free Microsoft documentation and code samples. No authentication required.",
    icon="microsoft_learn",
    category="development",
    tags=("docs", "documentation", "microsoft", "azure", "dotnet"),
    docs_url="https://learn.microsoft.com/en-us/training/support/mcp",
    target=lambda install: HttpTarget(MICROSOFT_LEARN_MCP_URL, {}),
)
