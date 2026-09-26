from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from src.connectors.mcp.models import MCPOAuthAuthConfig

if TYPE_CHECKING:
    from src.connectors.mcp.delivery import OAuthDelivery


@dataclass(frozen=True)
class HttpTarget:
    """A remote Streamable HTTP MCP server."""

    url: str
    headers: dict[str, str] = field(default_factory=dict)

    def with_header(self, name: str, value: str) -> "HttpTarget":
        return replace(self, headers={**self.headers, name: value})


@dataclass(frozen=True)
class StdioTarget:
    """A stdio MCP server hosted on the sidecar, launched from a baked package."""

    package: str
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    # env name -> file content. The sidecar writes each file 0600 and sets the env var to its path.
    files: dict[str, str] = field(default_factory=dict)

    def with_env(self, name: str, value: str) -> "StdioTarget":
        return replace(self, env={**self.env, name: value})

    def with_file(self, name: str, content: str) -> "StdioTarget":
        return replace(self, files={**self.files, name: content})


MCPTarget = HttpTarget | StdioTarget


@dataclass(frozen=True)
class OAuthBinding:
    """OAuth config and stored credentials, plus how the credential reaches the server."""

    auth: MCPOAuthAuthConfig
    delivery: "OAuthDelivery"


@dataclass(frozen=True)
class ResolvedConnection:
    """Everything needed to open a session: where the server is, and how it is authenticated.

    Static credentials are already applied to the target. OAuth credentials change over time, so they stay in
    the binding and are applied after refresh.
    """

    target: MCPTarget
    oauth: OAuthBinding | None = None
