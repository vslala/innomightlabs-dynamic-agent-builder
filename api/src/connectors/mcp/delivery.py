from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol, TypeVar

from src.connectors.mcp.models import MCPOAuthCredentials, MCPOAuthProviderConfig
from src.connectors.mcp.resolved import HttpTarget, MCPTarget, StdioTarget


class OAuthDelivery(Protocol):
    """How an OAuth credential reaches an MCP server."""

    @property
    def kind(self) -> str: ...

    @property
    def refresh_buffer_seconds(self) -> int:
        """How early to refresh before handing the credential over."""
        ...

    def apply(
        self,
        target: MCPTarget,
        provider: MCPOAuthProviderConfig,
        credentials: MCPOAuthCredentials,
    ) -> MCPTarget: ...


@dataclass(frozen=True)
class BearerHeader:
    """Remote servers: `Authorization: <type> <access token>` on every request."""

    kind: str = "bearer_header"
    refresh_buffer_seconds: int = 60

    def apply(
        self,
        target: MCPTarget,
        provider: MCPOAuthProviderConfig,
        credentials: MCPOAuthCredentials,
    ) -> HttpTarget:
        return _require(target, HttpTarget, self.kind).with_header(
            "Authorization",
            f"{normalize_token_type(credentials.token_type)} {credentials.access_token}",
        )


@dataclass(frozen=True)
class AccessTokenEnv:
    """Stdio servers that read an access token from their env.

    The process cannot refresh the token, so a refreshed token changes the launch spec and the sidecar
    restarts the process with the new value.
    """

    env_name: str
    kind: str = "access_token_env"
    # Refresh well before expiry so a token handed to a (re)started process outlives the calls it serves.
    refresh_buffer_seconds: int = 300

    def apply(
        self,
        target: MCPTarget,
        provider: MCPOAuthProviderConfig,
        credentials: MCPOAuthCredentials,
    ) -> StdioTarget:
        return _require(target, StdioTarget, self.kind).with_env(self.env_name, credentials.access_token)


@dataclass(frozen=True)
class GoogleAuthorizedUserFile:
    """Stdio servers using Google Application Default Credentials.

    The file is what `gcloud auth application-default login` writes: the user's OAuth client and refresh
    token. google-auth refreshes access tokens itself, so the file stays stable and the process never
    restarts on refresh.
    """

    env_name: str = "GOOGLE_APPLICATION_CREDENTIALS"
    kind: str = "google_authorized_user_file"
    refresh_buffer_seconds: int = 60

    def apply(
        self,
        target: MCPTarget,
        provider: MCPOAuthProviderConfig,
        credentials: MCPOAuthCredentials,
    ) -> StdioTarget:
        if not credentials.refresh_token:
            raise ValueError("The provider did not return a refresh token. Sign in again.")
        content = json.dumps(
            {
                "type": "authorized_user",
                "client_id": provider.client_id,
                "client_secret": provider.client_secret,
                "refresh_token": credentials.refresh_token,
            }
        )
        return _require(target, StdioTarget, self.kind).with_file(self.env_name, content)


# Stdio connectors choose their delivery by name; remote connectors always use BearerHeader.
STDIO_OAUTH_DELIVERIES: dict[str, type[AccessTokenEnv] | type[GoogleAuthorizedUserFile]] = {
    "access_token_env": AccessTokenEnv,
    "google_authorized_user_file": GoogleAuthorizedUserFile,
}


def stdio_oauth_delivery(kind: str, env_name: str) -> OAuthDelivery:
    delivery_type = STDIO_OAUTH_DELIVERIES.get(kind)
    if delivery_type is None:
        raise ValueError(f"Unsupported OAuth delivery: {kind}")
    return delivery_type(env_name=env_name)


def normalize_token_type(token_type: str) -> str:
    return "Bearer" if token_type.strip().lower() == "bearer" else token_type.strip()


_Target = TypeVar("_Target", HttpTarget, StdioTarget)


def _require(target: MCPTarget, target_type: type[_Target], delivery_kind: str) -> _Target:
    if not isinstance(target, target_type):
        raise ValueError(f"OAuth delivery '{delivery_kind}' cannot be used with this MCP transport")
    return target
