from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from pydantic import BaseModel, Field, ValidationError

from src.config import settings
from src.crypto import decrypt, encrypt
from src.db import get_dynamodb_resource
from src.skills.agent2agent_client.models import A2ARegistryConfig


class A2ARemoteOAuthError(ValueError):
    """Raised when a remote A2A OAuth operation cannot be completed."""


class A2ARemoteOAuthCredentials(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime
    token_type: str = "Bearer"
    scope: str = ""

    def is_expiring_soon(self) -> bool:
        return self.expires_at <= datetime.now(timezone.utc) + timedelta(minutes=5)


class A2ARemoteOAuthProviderConfig(BaseModel):
    authorization_url: str
    token_url: str
    refresh_url: str | None = None
    client_id: str
    client_secret: str | None = None
    scope: str = ""
    target_origin: str
    pkce_required: bool = True


class A2ARemoteOAuthAuthConfig(BaseModel):
    provider: A2ARemoteOAuthProviderConfig
    credentials: A2ARemoteOAuthCredentials | None = None


class A2ARemoteOAuthState(BaseModel):
    nonce: str
    code_verifier: str
    user_email: str
    agent_id: str
    installed_skill_id: str
    target_origin: str
    service_url: str
    return_to: str
    provider: A2ARemoteOAuthProviderConfig
    expires_at: int

    def is_expired(self) -> bool:
        return int(datetime.now(timezone.utc).timestamp()) > self.expires_at


class A2ARemoteOAuthCredentialRecord(BaseModel):
    owner_email: str
    agent_id: str
    installed_skill_id: str
    target_origin: str
    encrypted_auth_config: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None

    @property
    def pk(self) -> str:
        return f"User#{self.owner_email}"

    @property
    def sk(self) -> str:
        return f"A2ARemoteOAuthCredential#{self.installed_skill_id}#{_target_hash(self.target_origin)}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "entity_type": "A2ARemoteOAuthCredential",
            "owner_email": self.owner_email,
            "agent_id": self.agent_id,
            "installed_skill_id": self.installed_skill_id,
            "target_origin": self.target_origin,
            "encrypted_auth_config": self.encrypted_auth_config,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "A2ARemoteOAuthCredentialRecord":
        return cls(
            owner_email=item["owner_email"],
            agent_id=item["agent_id"],
            installed_skill_id=item["installed_skill_id"],
            target_origin=item["target_origin"],
            encrypted_auth_config=item["encrypted_auth_config"],
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )


class A2ARemoteOAuthRepository:
    def __init__(self) -> None:
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, record: A2ARemoteOAuthCredentialRecord) -> A2ARemoteOAuthCredentialRecord:
        existing = self.find(
            owner_email=record.owner_email,
            installed_skill_id=record.installed_skill_id,
            target_origin=record.target_origin,
        )
        if existing:
            record.created_at = existing.created_at
            record.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=record.to_dynamo_item())
        return record

    def find(
        self,
        *,
        owner_email: str,
        installed_skill_id: str,
        target_origin: str,
    ) -> A2ARemoteOAuthCredentialRecord | None:
        response = self.table.get_item(
            Key={
                "pk": f"User#{owner_email}",
                "sk": f"A2ARemoteOAuthCredential#{installed_skill_id}#{_target_hash(target_origin)}",
            }
        )
        item = response.get("Item")
        return A2ARemoteOAuthCredentialRecord.from_dynamo_item(item) if item else None


def authorization_code_provider_from_card(
    *,
    card: dict[str, Any],
    target_url: str,
    config: A2ARegistryConfig,
) -> A2ARemoteOAuthProviderConfig | None:
    flow = _authorization_code_flow(card)
    if not flow:
        return None

    target_origin = _origin(target_url)
    authorization_url = str(flow.get("authorizationUrl") or flow.get("authorization_url") or "").strip()
    token_url = str(flow.get("tokenUrl") or flow.get("token_url") or "").strip()
    refresh_url = str(flow.get("refreshUrl") or flow.get("refresh_url") or "").strip() or None
    if not authorization_url or not token_url:
        return None
    if not _oauth_endpoint_allowed(authorization_url, target_url=target_url, config=config):
        raise A2ARemoteOAuthError("Remote A2A OAuth authorization endpoint is outside the configured A2A origins")
    if not _oauth_endpoint_allowed(token_url, target_url=target_url, config=config):
        raise A2ARemoteOAuthError("Remote A2A OAuth token endpoint is outside the configured A2A origins")

    client = _parse_oauth_client_config(_find_credential(target_url=target_url, config=config))
    if not client:
        return None
    scopes = _required_scopes(card) or list(flow.get("scopes", {}).keys())
    return A2ARemoteOAuthProviderConfig(
        authorization_url=authorization_url,
        token_url=token_url,
        refresh_url=refresh_url,
        client_id=client["client_id"],
        client_secret=client.get("client_secret"),
        scope=" ".join(str(scope).strip() for scope in scopes if str(scope).strip()),
        target_origin=target_origin,
        pkce_required=bool(flow.get("pkceRequired", flow.get("pkce_required", True))),
    )


async def authorization_code_provider_from_card_with_dcr(
    *,
    card: dict[str, Any],
    target_url: str,
    config: A2ARegistryConfig,
) -> A2ARemoteOAuthProviderConfig | None:
    try:
        provider = authorization_code_provider_from_card(
            card=card,
            target_url=target_url,
            config=config,
        )
    except A2ARemoteOAuthError:
        provider = None
    if provider:
        return provider

    flow = _authorization_code_flow(card)
    if not flow:
        return None

    target_origin = _origin(target_url)
    authorization_url = str(flow.get("authorizationUrl") or flow.get("authorization_url") or "").strip()
    token_url = str(flow.get("tokenUrl") or flow.get("token_url") or "").strip()
    refresh_url = str(flow.get("refreshUrl") or flow.get("refresh_url") or "").strip() or None
    if not authorization_url or not token_url:
        return None

    scopes = _required_scopes(card) or list(flow.get("scopes", {}).keys())
    scope = " ".join(str(scope).strip() for scope in scopes if str(scope).strip())
    auth_metadata = await _discover_authorization_server_metadata(target_url)
    registration_endpoint = str(auth_metadata.get("registration_endpoint") or "").strip()
    if not registration_endpoint:
        raise A2ARemoteOAuthError("Remote A2A OAuth authorization server does not advertise Dynamic Client Registration")

    registered = await _register_client(
        registration_endpoint=registration_endpoint,
        scope=scope,
    )
    client_id = str(registered.get("client_id") or "").strip()
    if not client_id:
        raise A2ARemoteOAuthError("Remote A2A Dynamic Client Registration response missing client_id")

    return A2ARemoteOAuthProviderConfig(
        authorization_url=authorization_url,
        token_url=token_url,
        refresh_url=refresh_url,
        client_id=client_id,
        client_secret=str(registered.get("client_secret") or "").strip() or None,
        scope=str(registered.get("scope") or scope),
        target_origin=target_origin,
        pkce_required=bool(flow.get("pkceRequired", flow.get("pkce_required", True))),
    )


def build_authorization_url(
    *,
    provider: A2ARemoteOAuthProviderConfig,
    state: str,
    code_challenge: str,
) -> str:
    params = {
        "response_type": "code",
        "client_id": provider.client_id,
        "redirect_uri": _redirect_uri(),
        "state": state,
    }
    if provider.scope:
        params["scope"] = provider.scope
    if provider.pkce_required:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
    params["prompt"] = "consent"
    return f"{provider.authorization_url}?{urlencode(params)}"


def create_state_session(
    *,
    user_email: str,
    agent_id: str,
    installed_skill_id: str,
    service_url: str,
    return_to: str,
    provider: A2ARemoteOAuthProviderConfig,
) -> A2ARemoteOAuthState:
    nonce, code_verifier = generate_pkce_bundle()
    return A2ARemoteOAuthState(
        nonce=nonce,
        code_verifier=code_verifier,
        user_email=user_email,
        agent_id=agent_id,
        installed_skill_id=installed_skill_id,
        target_origin=provider.target_origin,
        service_url=service_url,
        return_to=return_to,
        provider=provider,
        expires_at=int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
    )


def encode_state_session(session: A2ARemoteOAuthState) -> str:
    return encrypt(session.model_dump_json())


def decode_state_session(state: str | None) -> A2ARemoteOAuthState | None:
    if not state:
        return None
    try:
        return A2ARemoteOAuthState.model_validate_json(decrypt(state))
    except (ValidationError, Exception):
        return None


async def exchange_code_for_tokens(
    *,
    provider: A2ARemoteOAuthProviderConfig,
    code: str,
    code_verifier: str,
) -> dict[str, Any]:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _redirect_uri(),
        "client_id": provider.client_id,
    }
    if provider.pkce_required:
        data["code_verifier"] = code_verifier
    if provider.client_secret:
        data["client_secret"] = provider.client_secret
    return await _post_token(provider.token_url, data)


async def refresh_access_token(
    *,
    provider: A2ARemoteOAuthProviderConfig,
    refresh_token: str,
) -> dict[str, Any]:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": provider.client_id,
    }
    if provider.client_secret:
        data["client_secret"] = provider.client_secret
    return await _post_token(provider.refresh_url or provider.token_url, data)


def build_credentials(
    tokens: dict[str, Any],
    *,
    previous: A2ARemoteOAuthCredentials | None = None,
    default_scope: str = "",
) -> A2ARemoteOAuthCredentials:
    access_token = str(tokens.get("access_token") or (previous.access_token if previous else "")).strip()
    if not access_token:
        raise A2ARemoteOAuthError("Remote A2A OAuth token response missing access_token")
    refresh_token = tokens.get("refresh_token") or (previous.refresh_token if previous else None)
    expires_in = int(tokens.get("expires_in") or 3600)
    return A2ARemoteOAuthCredentials(
        access_token=access_token,
        refresh_token=str(refresh_token) if refresh_token else None,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        token_type=str(tokens.get("token_type") or (previous.token_type if previous else "Bearer")),
        scope=str(tokens.get("scope") or (previous.scope if previous else default_scope)),
    )


def encrypt_auth_config(auth: A2ARemoteOAuthAuthConfig) -> str:
    return encrypt(auth.model_dump_json())


def decrypt_auth_config(record: A2ARemoteOAuthCredentialRecord) -> A2ARemoteOAuthAuthConfig:
    return A2ARemoteOAuthAuthConfig.model_validate(json.loads(decrypt(record.encrypted_auth_config)))


async def ensure_valid_access_token(
    *,
    record: A2ARemoteOAuthCredentialRecord,
    repository: A2ARemoteOAuthRepository,
) -> A2ARemoteOAuthCredentials:
    auth = decrypt_auth_config(record)
    if not auth.credentials:
        raise A2ARemoteOAuthError("Remote A2A OAuth credential has not been connected")
    if not auth.credentials.refresh_token:
        if auth.credentials.expires_at <= datetime.now(timezone.utc):
            raise A2ARemoteOAuthError("Remote A2A OAuth credential expired. Reconnect the remote agent.")
        return auth.credentials
    if not auth.credentials.is_expiring_soon():
        return auth.credentials

    tokens = await refresh_access_token(provider=auth.provider, refresh_token=auth.credentials.refresh_token)
    refreshed = build_credentials(tokens, previous=auth.credentials, default_scope=auth.provider.scope)
    record.encrypted_auth_config = encrypt_auth_config(
        A2ARemoteOAuthAuthConfig(provider=auth.provider, credentials=refreshed)
    )
    repository.save(record)
    return refreshed


def _redirect_uri() -> str:
    return f"{settings.api_base_url.rstrip('/')}/skills/agent2agent_client/oauth/callback"


def generate_pkce_bundle() -> tuple[str, str]:
    nonce = _base64url(secrets.token_bytes(32))
    code_verifier = _base64url(secrets.token_bytes(64))
    return nonce, code_verifier


def generate_code_challenge(code_verifier: str) -> str:
    return _base64url(hashlib.sha256(code_verifier.encode("utf-8")).digest())


async def _post_token(token_url: str, data: dict[str, str]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            token_url,
            data=data,
            headers={
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded",
            },
        )
    if not response.is_success:
        raise A2ARemoteOAuthError(f"Remote A2A OAuth token request failed: {response.text[:500]}")

    payload = _parse_token_response(response)
    if not isinstance(payload, dict):
        raise A2ARemoteOAuthError("Remote A2A OAuth token response must be a JSON object")
    return payload


def _parse_token_response(response: httpx.Response) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "").lower()
    if "json" in content_type:
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    if "application/x-www-form-urlencoded" in content_type:
        return _parse_form_encoded_token_response(response.text)
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return payload
    except ValueError:
        pass
    form_payload = _parse_form_encoded_token_response(response.text)
    if form_payload:
        return form_payload
    raise A2ARemoteOAuthError("Remote A2A OAuth token response must be JSON or form-encoded")


def _parse_form_encoded_token_response(body: str) -> dict[str, str]:
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items() if values}


def _authorization_code_flow(card: dict[str, Any]) -> dict[str, Any] | None:
    schemes = card.get("securitySchemes")
    if not isinstance(schemes, dict):
        return None
    for scheme in schemes.values():
        if not isinstance(scheme, dict):
            continue
        oauth2 = scheme.get("oauth2SecurityScheme") if isinstance(scheme.get("oauth2SecurityScheme"), dict) else scheme
        if not isinstance(oauth2, dict):
            continue
        flows = oauth2.get("flows")
        if not isinstance(flows, dict):
            continue
        flow = flows.get("authorizationCode") or flows.get("authorization_code")
        if isinstance(flow, dict):
            return flow
    return None


def has_authorization_code_flow(card: dict[str, Any]) -> bool:
    return _authorization_code_flow(card) is not None


def _required_scopes(card: dict[str, Any]) -> list[str]:
    requirements = card.get("securityRequirements") or card.get("security") or []
    if not isinstance(requirements, list):
        return []
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        schemes = requirement.get("schemes") if isinstance(requirement.get("schemes"), dict) else requirement
        if not isinstance(schemes, dict):
            continue
        for raw_scopes in schemes.values():
            if isinstance(raw_scopes, list):
                return [str(scope).strip() for scope in raw_scopes if str(scope).strip()]
            if isinstance(raw_scopes, dict) and isinstance(raw_scopes.get("list"), list):
                return [str(scope).strip() for scope in raw_scopes["list"] if str(scope).strip()]
    return []


def _parse_oauth_client_config(value: str) -> dict[str, str]:
    credential = value.strip()
    if not credential:
        return {}
    if credential.startswith("{"):
        try:
            payload = json.loads(credential)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        client_id = str(payload.get("client_id") or payload.get("clientId") or "").strip()
        client_secret = str(payload.get("client_secret") or payload.get("clientSecret") or "").strip()
        return {
            key: value
            for key, value in {"client_id": client_id, "client_secret": client_secret}.items()
            if value
        }
    client_id, separator, client_secret = credential.partition(":")
    if separator and client_id.strip() and client_secret.strip():
        return {"client_id": client_id.strip(), "client_secret": client_secret.strip()}
    return {}


def _find_credential(*, target_url: str, config: A2ARegistryConfig) -> str:
    candidates = [target_url.rstrip("/"), _origin(target_url)]
    for registry_url in config.registry_urls:
        candidates.extend([registry_url.rstrip("/"), _origin(registry_url)])
    for candidate in dict.fromkeys(item for item in candidates if item):
        credential = config.default_credentials.get(candidate)
        if credential:
            return credential
    return ""


def _oauth_endpoint_allowed(url: str, *, target_url: str, config: A2ARegistryConfig) -> bool:
    endpoint_origin = _origin(url)
    if not endpoint_origin:
        return False
    allowed_origins = {_origin(target_url)}
    allowed_origins.update(_origin(registry_url) for registry_url in config.registry_urls)
    return endpoint_origin in allowed_origins


async def _discover_authorization_server_metadata(target_url: str) -> dict[str, Any]:
    resource_metadata = await _fetch_first_json(_protected_resource_metadata_urls(target_url))
    authorization_servers = resource_metadata.get("authorization_servers")
    if not isinstance(authorization_servers, list) or not authorization_servers:
        raise A2ARemoteOAuthError("Remote A2A protected resource metadata missing authorization_servers")

    authorization_server = str(authorization_servers[0]).strip()
    if not authorization_server:
        raise A2ARemoteOAuthError("Remote A2A protected resource metadata returned an empty authorization server")
    return await _fetch_first_json(_authorization_server_metadata_urls(authorization_server))


def _protected_resource_metadata_urls(resource_url: str) -> list[str]:
    parsed = urlparse(resource_url)
    if not parsed.scheme or not parsed.netloc:
        return []
    origin = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")
    urls = []
    if path:
        urls.append(f"{origin}/.well-known/oauth-protected-resource{path}")
    urls.append(f"{origin}/.well-known/oauth-protected-resource")
    return list(dict.fromkeys(urls))


def _authorization_server_metadata_urls(authorization_server: str) -> list[str]:
    parsed = urlparse(authorization_server.strip().rstrip("/"))
    if not parsed.scheme or not parsed.netloc:
        raise A2ARemoteOAuthError("Remote A2A authorization server URL must include scheme and host")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")
    if path:
        return [
            f"{origin}/.well-known/oauth-authorization-server{path}",
            f"{origin}/.well-known/openid-configuration{path}",
            f"{origin}{path}/.well-known/openid-configuration",
        ]
    return [
        f"{origin}/.well-known/oauth-authorization-server",
        f"{origin}/.well-known/openid-configuration",
    ]


async def _fetch_json(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, headers={"accept": "application/json"})
    if not response.is_success:
        raise A2ARemoteOAuthError(f"Remote A2A OAuth metadata discovery failed at {url}: HTTP {response.status_code}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise A2ARemoteOAuthError(f"Remote A2A OAuth metadata discovery returned non-object JSON at {url}")
    return payload


async def _fetch_first_json(urls: list[str]) -> dict[str, Any]:
    errors: list[str] = []
    for url in urls:
        try:
            return await _fetch_json(url)
        except A2ARemoteOAuthError as exc:
            errors.append(str(exc))
    raise A2ARemoteOAuthError("; ".join(errors) if errors else "Remote A2A OAuth metadata discovery has no URLs to try")


async def _register_client(*, registration_endpoint: str, scope: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "client_name": "InnoMight Labs Agent2Agent Client",
        "redirect_uris": [_redirect_uri()],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    if scope:
        payload["scope"] = scope

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            registration_endpoint,
            headers={"accept": "application/json", "content-type": "application/json"},
            json=payload,
        )
    if not response.is_success:
        raise A2ARemoteOAuthError(f"Remote A2A Dynamic Client Registration failed: {response.text[:500]}")
    data = response.json()
    if not isinstance(data, dict):
        raise A2ARemoteOAuthError("Remote A2A Dynamic Client Registration response must be a JSON object")
    return data


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _target_hash(target_origin: str) -> str:
    return hashlib.sha256(target_origin.encode("utf-8")).hexdigest()[:24]


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")
