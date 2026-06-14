from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse, urlencode

import httpx
from pydantic import BaseModel, ValidationError

from src.connectors.mcp.models import MCPOAuthCredentials, MCPOAuthDiscoveryResponse, MCPOAuthProviderConfig
from src.config import settings
from src.crypto import decrypt, encrypt

MCP_PROTOCOL_VERSION = "2025-06-18"


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
    challenge = await _fetch_oauth_challenge(resource_url)
    resource_metadata = await _fetch_first_json(_protected_resource_metadata_urls(resource_url, challenge))
    authorization_servers = resource_metadata.get("authorization_servers")
    if not isinstance(authorization_servers, list) or not authorization_servers:
        raise MCPOAuthError("MCP protected resource metadata missing authorization_servers")

    authorization_server = str(authorization_servers[0]).strip()
    if not authorization_server:
        raise MCPOAuthError("MCP protected resource metadata returned an empty authorization server")

    auth_metadata = await _fetch_first_json(authorization_server_metadata_urls(authorization_server))
    authorization_endpoint = str(auth_metadata.get("authorization_endpoint") or "").strip()
    token_endpoint = str(auth_metadata.get("token_endpoint") or "").strip()
    if not authorization_endpoint or not token_endpoint:
        raise MCPOAuthError("OAuth authorization server metadata missing authorization_endpoint or token_endpoint")

    scope = challenge.get("scope", "")
    if not scope:
        scopes = resource_metadata.get("scopes_supported")
        scope = " ".join(str(item).strip() for item in scopes if str(item).strip()) if isinstance(scopes, list) else ""
    registration_endpoint = auth_metadata.get("registration_endpoint")
    token_endpoint_auth_methods = auth_metadata.get("token_endpoint_auth_methods_supported")
    registered = (
        await _register_client(
            str(registration_endpoint),
            scope,
            token_endpoint_auth_methods=[
                str(item).strip()
                for item in token_endpoint_auth_methods
                if str(item).strip()
            ]
            if isinstance(token_endpoint_auth_methods, list)
            else [],
        )
        if registration_endpoint
        else {}
    )

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


def protected_resource_metadata_url_for_path(resource_url: str) -> str:
    parsed = urlparse(resource_url)
    path = parsed.path.rstrip("/")
    if not path:
        return protected_resource_metadata_url(resource_url)
    return f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-protected-resource{path}"


def authorization_server_metadata_url(authorization_server: str) -> str:
    return authorization_server_metadata_urls(authorization_server)[0]


def authorization_server_metadata_urls(authorization_server: str) -> list[str]:
    parsed = urlparse(authorization_server.strip().rstrip("/"))
    if not parsed.scheme or not parsed.netloc:
        raise MCPOAuthError("Authorization server URL must include scheme and host")
    path = parsed.path.rstrip("/")
    if path:
        return [
            f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-authorization-server{path}",
            f"{parsed.scheme}://{parsed.netloc}/.well-known/openid-configuration{path}",
            f"{parsed.scheme}://{parsed.netloc}{path}/.well-known/openid-configuration",
        ]
    return [
        f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-authorization-server",
        f"{parsed.scheme}://{parsed.netloc}/.well-known/openid-configuration",
    ]


def parse_www_authenticate(headers: list[str]) -> dict[str, str]:
    for header in headers:
        scheme, _, rest = header.strip().partition(" ")
        if scheme.lower() != "bearer" or not rest:
            continue
        params = _parse_auth_params(rest)
        if params:
            return params
    return {}


def _protected_resource_metadata_urls(resource_url: str, challenge: dict[str, str]) -> list[str]:
    challenged_url = challenge.get("resource_metadata", "").strip()
    if challenged_url:
        return [challenged_url]

    path_url = protected_resource_metadata_url_for_path(resource_url)
    root_url = protected_resource_metadata_url(resource_url)
    if path_url == root_url:
        return [root_url]
    return [path_url, root_url]


async def _fetch_oauth_challenge(resource_url: str) -> dict[str, str]:
    payload = {
        "jsonrpc": "2.0",
        "id": "oauth-discovery",
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {
                "name": "innomightlabs",
                "title": "InnoMight Labs",
                "version": "1.0.0",
            },
        },
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(resource_url, headers=headers, json=payload)

    if response.status_code != 401:
        return {}

    return parse_www_authenticate(response.headers.get_list("www-authenticate"))


async def _fetch_json(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url)
    if not response.is_success:
        raise MCPOAuthError(f"OAuth metadata discovery failed at {url}: HTTP {response.status_code}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise MCPOAuthError(f"OAuth metadata discovery returned non-object JSON at {url}")
    return payload


async def _fetch_first_json(urls: list[str]) -> dict[str, Any]:
    errors: list[str] = []
    for url in urls:
        try:
            return await _fetch_json(url)
        except MCPOAuthError as exc:
            errors.append(str(exc))
    raise MCPOAuthError("; ".join(errors) if errors else "OAuth metadata discovery has no URLs to try")


async def _register_client(
    registration_endpoint: str,
    scope: str,
    *,
    token_endpoint_auth_methods: list[str] | None = None,
) -> dict[str, Any]:
    endpoint = registration_endpoint.strip()
    if not endpoint:
        return {}

    token_endpoint_auth_method = _select_token_endpoint_auth_method(token_endpoint_auth_methods or [])
    payload: dict[str, Any] = {
        "client_name": "InnoMight Labs",
        "redirect_uris": [settings.mcp_oauth_redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": token_endpoint_auth_method,
    }
    if scope:
        payload["scope"] = scope

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(endpoint, json=payload)
    if not response.is_success:
        return {}

    data = response.json()
    return data if isinstance(data, dict) else {}


def _select_token_endpoint_auth_method(supported_methods: list[str]) -> str:
    normalized = {method.strip().lower() for method in supported_methods if method.strip()}
    if not normalized or "client_secret_post" in normalized:
        return "client_secret_post"
    if "none" in normalized:
        return "none"
    return "client_secret_post"


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


def _parse_auth_params(value: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for part in _split_auth_params(value):
        key, separator, raw_value = part.partition("=")
        if not separator:
            continue
        cleaned_key = key.strip().lower()
        if not cleaned_key:
            continue
        params[cleaned_key] = _unquote_auth_param(raw_value.strip())
    return params


def _split_auth_params(value: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    in_quotes = False
    escaped = False
    for char in value:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\" and in_quotes:
            current.append(char)
            escaped = True
            continue
        if char == '"':
            current.append(char)
            in_quotes = not in_quotes
            continue
        if char == "," and not in_quotes:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            continue
        current.append(char)
    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts


def _unquote_auth_param(value: str) -> str:
    if len(value) < 2 or value[0] != '"' or value[-1] != '"':
        return value
    try:
        decoded = json.loads(value)
    except ValueError:
        return value[1:-1]
    return decoded if isinstance(decoded, str) else value[1:-1]
