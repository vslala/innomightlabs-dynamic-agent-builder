from __future__ import annotations

import base64
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, Request

from src.apikeys.models import AgentApiKey
from src.apikeys.repository import ApiKeyRepository
from src.config import settings

A2A_OAUTH_TOKEN_USE = "a2a_access_token"
A2A_OAUTH_AUDIENCE = "innomightlabs:a2a"
A2A_SCOPE_MESSAGE = "a2a:message"
A2A_SCOPE_TASKS = "a2a:tasks"
A2A_SCOPES = {
    A2A_SCOPE_MESSAGE: "Send A2A messages to an enabled agent.",
    A2A_SCOPE_TASKS: "Read and manage A2A tasks for an enabled agent.",
}
DEFAULT_A2A_SCOPES = set(A2A_SCOPES)


@dataclass(frozen=True)
class A2AOAuthClientCredentials:
    client_id: str
    client_secret: str
    scope: str


def a2a_oauth_issuer() -> str:
    return f"{settings.api_base_url.rstrip('/')}/a2a/oauth"


def a2a_oauth_token_url() -> str:
    return f"{settings.api_base_url.rstrip('/')}/a2a/oauth/token"


def a2a_oauth_metadata_url() -> str:
    return f"{settings.api_base_url.rstrip('/')}/a2a/oauth/.well-known/oauth-authorization-server"


def a2a_oauth_token_ttl_seconds() -> int:
    return max(60, min(24 * 60 * 60, int(settings.a2a_oauth_access_token_ttl_seconds or 3600)))


async def parse_client_credentials_request(request: Request) -> A2AOAuthClientCredentials:
    basic_client_id, basic_client_secret = _parse_basic_auth(request.headers.get("Authorization"))
    content_type = request.headers.get("content-type", "")
    form: dict[str, str] = {}
    if "application/x-www-form-urlencoded" in content_type:
        body = (await request.body()).decode("utf-8")
        form = _parse_urlencoded_body(body)

    client_id = basic_client_id or form.get("client_id", "")
    client_secret = basic_client_secret or form.get("client_secret", "")
    scope = form.get("scope", "")
    grant_type = form.get("grant_type", "")

    if grant_type != "client_credentials":
        raise _oauth_error("unsupported_grant_type", "Only client_credentials grant is supported", status_code=400)
    if not client_id or not client_secret:
        raise _oauth_error("invalid_client", "Missing OAuth client credentials", status_code=401)
    return A2AOAuthClientCredentials(client_id=client_id, client_secret=client_secret, scope=scope)


def issue_a2a_access_token(*, api_key: AgentApiKey, requested_scope: str | None = None) -> dict[str, Any]:
    scopes = _normalize_requested_scopes(requested_scope)
    now = datetime.now(timezone.utc)
    expires_in = a2a_oauth_token_ttl_seconds()
    payload = {
        "iss": a2a_oauth_issuer(),
        "aud": A2A_OAUTH_AUDIENCE,
        "sub": f"agent:{api_key.agent_id}:api_key:{api_key.key_id}",
        "token_use": A2A_OAUTH_TOKEN_USE,
        "agent_id": api_key.agent_id,
        "client_key_id": api_key.key_id,
        "owner_email": api_key.created_by,
        "scope": " ".join(sorted(scopes)),
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "jti": secrets.token_urlsafe(24),
    }
    access_token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "scope": payload["scope"],
    }


def validate_a2a_access_token(
    *,
    token: str,
    agent_id: str,
    api_key_repo: ApiKeyRepository,
    required_scopes: set[str],
) -> AgentApiKey:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=A2A_OAUTH_AUDIENCE,
            issuer=a2a_oauth_issuer(),
        )
    except jwt.ExpiredSignatureError as exc:
        raise _oauth_error("invalid_token", "A2A OAuth token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise _oauth_error("invalid_token", "Invalid A2A OAuth token") from exc

    if payload.get("token_use") != A2A_OAUTH_TOKEN_USE:
        raise _oauth_error("invalid_token", "Invalid A2A OAuth token use")
    if payload.get("agent_id") != agent_id:
        raise _oauth_error("invalid_token", "A2A OAuth token is not valid for this agent")

    token_scopes = set(str(payload.get("scope") or "").split())
    if required_scopes and not required_scopes.issubset(token_scopes):
        raise _oauth_error("insufficient_scope", "A2A OAuth token is missing required scope", status_code=403)

    client_key_id = str(payload.get("client_key_id") or "")
    api_key = api_key_repo.find_by_id(agent_id, client_key_id)
    if not api_key or not api_key.is_active or api_key.created_by != payload.get("owner_email"):
        raise _oauth_error("invalid_token", "A2A OAuth token client has been revoked")
    return api_key


def validate_client_credentials(
    *,
    credentials: A2AOAuthClientCredentials,
    api_key_repo: ApiKeyRepository,
) -> AgentApiKey:
    api_key = api_key_repo.find_by_public_key(credentials.client_secret)
    if not api_key or not api_key.is_active or api_key.key_id != credentials.client_id:
        raise _oauth_error("invalid_client", "Invalid OAuth client credentials", status_code=401)
    _normalize_requested_scopes(credentials.scope)
    return api_key


def oauth_metadata() -> dict[str, Any]:
    return {
        "issuer": a2a_oauth_issuer(),
        "token_endpoint": a2a_oauth_token_url(),
        "grant_types_supported": ["client_credentials"],
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
        "scopes_supported": sorted(A2A_SCOPES),
        "response_types_supported": [],
    }


def bearer_challenge(*, error: str | None = None, scope: str | None = None) -> dict[str, str]:
    parts = ['Bearer realm="a2a"']
    if error:
        parts.append(f'error="{error}"')
    if scope:
        parts.append(f'scope="{scope}"')
    return {"WWW-Authenticate": ", ".join(parts)}


def _normalize_requested_scopes(raw_scope: str | None) -> set[str]:
    if not raw_scope:
        return set(DEFAULT_A2A_SCOPES)
    scopes = {item.strip() for item in raw_scope.split() if item.strip()}
    unknown = scopes.difference(A2A_SCOPES)
    if unknown:
        raise _oauth_error(
            "invalid_scope",
            f"Unsupported A2A OAuth scope: {', '.join(sorted(unknown))}",
            status_code=400,
        )
    return scopes


def _parse_basic_auth(value: str | None) -> tuple[str, str]:
    if not value:
        return "", ""
    scheme, _, encoded = value.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return "", ""
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except Exception:
        raise _oauth_error("invalid_client", "Invalid Basic authentication header", status_code=401)
    client_id, separator, client_secret = decoded.partition(":")
    if not separator:
        raise _oauth_error("invalid_client", "Invalid Basic authentication header", status_code=401)
    return client_id, client_secret


def _parse_urlencoded_body(body: str) -> dict[str, str]:
    from urllib.parse import parse_qsl

    return {key: value for key, value in parse_qsl(body, keep_blank_values=True)}


def _oauth_error(error: str, description: str, *, status_code: int = 401) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": error, "error_description": description},
        headers=bearer_challenge(error=error),
    )
