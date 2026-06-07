from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse, urlencode

import httpx
from pydantic import BaseModel, ValidationError

from src.connectors.mcp.models import MCPOAuthCredentials, MCPOAuthDiscoveryResponse, MCPOAuthProviderConfig
from src.config import settings
from src.crypto import decrypt, encrypt


class MCPOAuthError(ValueError):
    """Raised when a generic MCP OAuth operation fails."""


class MCPOAuthState(BaseModel):
    nonce: str
    code_verifier: str
    user_email: str
    mcp_id: str
    return_to: str
    expires_at: int

    def is_expired(self) -> bool:
        return int(datetime.now(timezone.utc).timestamp()) > self.expires_at


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def generate_pkce_bundle() -> tuple[str, str]:
    nonce = _base64url(secrets.token_bytes(32))
    code_verifier = _base64url(secrets.token_bytes(64))
    return nonce, code_verifier


def generate_code_challenge(code_verifier: str) -> str:
    return _base64url(hashlib.sha256(code_verifier.encode("utf-8")).digest())


def encode_state_session(session: MCPOAuthState) -> str:
    return encrypt(session.model_dump_json())


def decode_state_session(state: str | None) -> Optional[MCPOAuthState]:
    if not state:
        return None
    try:
        return MCPOAuthState.model_validate_json(decrypt(state))
    except (ValidationError, Exception):
        return None


def create_state_session(*, user_email: str, mcp_id: str, return_to: str) -> MCPOAuthState:
    nonce, code_verifier = generate_pkce_bundle()
    return MCPOAuthState(
        nonce=nonce,
        code_verifier=code_verifier,
        user_email=user_email,
        mcp_id=mcp_id,
        return_to=return_to,
        expires_at=int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
    )


def build_authorization_url(
    *,
    provider: MCPOAuthProviderConfig,
    state: str,
    code_challenge: str,
) -> str:
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": provider.client_id,
        "redirect_uri": settings.mcp_oauth_redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "resource": provider.resource_url,
    }
    if provider.scope:
        params["scope"] = provider.scope
    return f"{provider.authorization_url}?{urlencode(params)}"


async def exchange_code_for_tokens(
    *,
    provider: MCPOAuthProviderConfig,
    code: str,
    code_verifier: str,
) -> dict[str, Any]:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.mcp_oauth_redirect_uri,
        "client_id": provider.client_id,
        "code_verifier": code_verifier,
        "resource": provider.resource_url,
    }
    if provider.client_secret:
        data["client_secret"] = provider.client_secret

    return await _post_token(str(provider.token_url), data)


async def refresh_access_token(
    *,
    provider: MCPOAuthProviderConfig,
    refresh_token: str,
) -> dict[str, Any]:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": provider.client_id,
        "resource": provider.resource_url,
    }
    if provider.client_secret:
        data["client_secret"] = provider.client_secret

    return await _post_token(str(provider.token_url), data)


async def discover_oauth_provider(server_url: str) -> MCPOAuthDiscoveryResponse:
    resource_url = canonical_resource_url(server_url)
    resource_metadata = await _fetch_json(protected_resource_metadata_url(resource_url))
    authorization_servers = resource_metadata.get("authorization_servers")
    if not isinstance(authorization_servers, list) or not authorization_servers:
        raise MCPOAuthError("MCP protected resource metadata missing authorization_servers")

    authorization_server = str(authorization_servers[0]).strip()
    if not authorization_server:
        raise MCPOAuthError("MCP protected resource metadata returned an empty authorization server")

    auth_metadata = await _fetch_json(authorization_server_metadata_url(authorization_server))
    authorization_endpoint = str(auth_metadata.get("authorization_endpoint") or "").strip()
    token_endpoint = str(auth_metadata.get("token_endpoint") or "").strip()
    if not authorization_endpoint or not token_endpoint:
        raise MCPOAuthError("OAuth authorization server metadata missing authorization_endpoint or token_endpoint")

    scopes = auth_metadata.get("scopes_supported")
    scope = " ".join(str(item).strip() for item in scopes if str(item).strip()) if isinstance(scopes, list) else ""
    registration_endpoint = auth_metadata.get("registration_endpoint")
    registered = await _register_client(str(registration_endpoint), scope) if registration_endpoint else {}

    return MCPOAuthDiscoveryResponse(
        authorization_url=authorization_endpoint,
        token_url=token_endpoint,
        client_id=str(registered.get("client_id") or ""),
        client_secret=str(registered.get("client_secret") or ""),
        scope=str(registered.get("scope") or scope),
        resource_url=resource_url,
        authorization_server=authorization_server,
        registration_endpoint=str(registration_endpoint) if registration_endpoint else None,
        registered_client=bool(registered.get("client_id")),
    )


def canonical_resource_url(server_url: str) -> str:
    parsed = urlparse(server_url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise MCPOAuthError("MCP server URL must include scheme and host")
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    return f"{scheme}://{host}{path}" if path else f"{scheme}://{host}"


def protected_resource_metadata_url(resource_url: str) -> str:
    parsed = urlparse(resource_url)
    return f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-protected-resource"


def authorization_server_metadata_url(authorization_server: str) -> str:
    parsed = urlparse(authorization_server.strip().rstrip("/"))
    if not parsed.scheme or not parsed.netloc:
        raise MCPOAuthError("Authorization server URL must include scheme and host")
    path = parsed.path.rstrip("/")
    if path:
        return f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-authorization-server{path}"
    return f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-authorization-server"


async def _fetch_json(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url)
    if not response.is_success:
        raise MCPOAuthError(f"OAuth metadata discovery failed at {url}: HTTP {response.status_code}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise MCPOAuthError(f"OAuth metadata discovery returned non-object JSON at {url}")
    return payload


async def _register_client(registration_endpoint: str, scope: str) -> dict[str, Any]:
    endpoint = registration_endpoint.strip()
    if not endpoint:
        return {}

    payload: dict[str, Any] = {
        "client_name": "InnoMight Labs",
        "redirect_uris": [settings.mcp_oauth_redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "client_secret_post",
    }
    if scope:
        payload["scope"] = scope

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(endpoint, json=payload)
    if not response.is_success:
        return {}

    data = response.json()
    return data if isinstance(data, dict) else {}


async def _post_token(token_url: str, data: dict[str, str]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            token_url,
            data=data,
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
    if not response.is_success:
        raise MCPOAuthError(f"MCP OAuth token request failed: {response.text}")

    payload = response.json()
    if not isinstance(payload, dict):
        raise MCPOAuthError("MCP OAuth token response must be a JSON object")
    return payload


def build_credentials(
    tokens: dict[str, Any],
    *,
    previous: Optional[MCPOAuthCredentials] = None,
    default_scope: str = "",
) -> MCPOAuthCredentials:
    access_token = str(tokens.get("access_token") or (previous.access_token if previous else "")).strip()
    if not access_token:
        raise MCPOAuthError("MCP OAuth token response missing access_token")

    refresh_token = tokens.get("refresh_token") or (previous.refresh_token if previous else None)
    expires_in = int(tokens.get("expires_in") or 3600)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    return MCPOAuthCredentials(
        access_token=access_token,
        refresh_token=str(refresh_token) if refresh_token else None,
        expires_at=expires_at,
        token_type=str(tokens.get("token_type") or (previous.token_type if previous else "Bearer")),
        scope=str(tokens.get("scope") or (previous.scope if previous else default_scope)),
    )
