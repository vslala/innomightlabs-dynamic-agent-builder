from __future__ import annotations

from src.connectors.mcp.providers.base import MCPProvider
from src.connectors.mcp.resolved import HttpTarget

DEEPWIKI_MCP_URL = "https://mcp.deepwiki.com/mcp"


PROVIDER = MCPProvider(
    key="deepwiki",
    display_name="DeepWiki",
    description="Free documentation and questions about public GitHub repositories. No authentication required.",
    icon="deepwiki",
    category="development",
    tags=("docs", "documentation", "github", "repositories", "coding"),
    docs_url="https://deepwiki.com",
    target=lambda install: HttpTarget(DEEPWIKI_MCP_URL, {}),
)
