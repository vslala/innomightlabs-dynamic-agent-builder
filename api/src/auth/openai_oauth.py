import base64
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ValidationError

from src.config import settings
from src.crypto import decrypt, encrypt
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository

log = logging.getLogger(__name__)

OPENAI_AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
OPENAI_TOKEN_URL = "https://auth.openai.com/oauth/token"


class OpenAIOAuthError(Exception):
    """Raised when OpenAI OAuth operations fail."""


class OpenAICredentials(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: datetime
    account_id: Optional[str] = None
    id_token: Optional[str] = None
    scope: str = ""
    token_type: str = "Bearer"

    def is_expiring_soon(self, refresh_buffer_seconds: int = 60) -> bool:
        now = datetime.now(timezone.utc)
        return (self.expires_at - now).total_seconds() <= refresh_buffer_seconds


class OpenAIOAuthState(BaseModel):
    nonce: str
    code_verifier: str
    user_email: str
    return_to: str
    expires_at: int

    def is_expired(self) -> bool:
        now_ts = int(datetime.now(timezone.utc).timestamp())
        return now_ts > self.expires_at


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def generate_pkce_bundle() -> tuple[str, str]:
    """
    Generate nonce and code_verifier for PKCE flow.
    """
    nonce = _base64url(secrets.token_bytes(32))
    code_verifier = _base64url(secrets.token_bytes(64))
    return nonce, code_verifier


def generate_code_challenge(code_verifier: str) -> str:
    return _base64url(hashlib.sha256(code_verifier.encode("utf-8")).digest())


def build_authorization_url(state: str, code_challenge: str) -> str:
    """
    Build OpenAI OAuth authorize URL from environment-driven contract.
    """
    if not settings.openai_oauth_client_id:
        raise OpenAIOAuthError("OpenAI OAuth client is not configured")

    params: dict[str, str] = {
        "response_type": "code",
        "client_id": settings.openai_oauth_client_id,
        "redirect_uri": settings.openai_oauth_redirect_uri,
        "scope": settings.openai_oauth_scopes,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }

    if settings.openai_oauth_id_token_add_organizations:
        params["id_token_add_organizations"] = "true"
    if settings.openai_oauth_codex_cli_simplified_flow:
        params["codex_cli_simplified_flow"] = "true"
    if settings.openai_oauth_originator:
        params["originator"] = settings.openai_oauth_originator

    return f"{OPENAI_AUTHORIZE_URL}?{urlencode(params)}"


def encode_state_session(session: OpenAIOAuthState) -> str:
    return encrypt(session.model_dump_json())


def decode_state_session(state: str | None) -> Optional[OpenAIOAuthState]:
    if not state:
        return None

    try:
        decoded = decrypt(state)
        return OpenAIOAuthState.model_validate_json(decoded)
    except (ValidationError, Exception):
        return None


async def exchange_code_for_tokens(code: str, code_verifier: str) -> dict[str, Any]:
    """Exchange OAuth authorization code for tokens."""
    if not settings.openai_oauth_client_id:
        raise OpenAIOAuthError("OpenAI OAuth client is not configured")

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            OPENAI_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.openai_oauth_redirect_uri,
                "client_id": settings.openai_oauth_client_id,
                "code_verifier": code_verifier,
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    if not response.is_success:
        raise OpenAIOAuthError(f"Token exchange failed: {response.text}")

    payload = response.json()
    return payload if isinstance(payload, dict) else {}


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    """Refresh an OpenAI OAuth access token."""
    if not settings.openai_oauth_client_id:
        raise OpenAIOAuthError("OpenAI OAuth client is not configured")

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            OPENAI_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.openai_oauth_client_id,
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    if not response.is_success:
        raise OpenAIOAuthError(f"Token refresh failed: {response.text}")

    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def extract_account_id_from_access_token(access_token: str) -> Optional[str]:
    """Best-effort account id extraction from JWT-like access token payload."""
    try:
        parts = access_token.split(".")
        if len(parts) < 2:
            return None

        payload = parts[1]
        padded = payload + "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        claims = json.loads(decoded)

        for key in ("account_id", "accountId", "org_id", "sub"):
            value = claims.get(key)
            if isinstance(value, str) and value:
                return value
    except Exception:
        return None

    return None


def _build_credentials(tokens: dict[str, Any], previous: Optional[OpenAICredentials] = None) -> OpenAICredentials:
    previous = previous or OpenAICredentials(
        access_token="",
        refresh_token=None,
        expires_at=datetime.now(timezone.utc),
        account_id=None,
        id_token=None,
        scope=settings.openai_oauth_scopes,
        token_type="Bearer",
    )

    access_token = tokens.get("access_token") or previous.access_token
    if not access_token:
        raise OpenAIOAuthError("OpenAI token response missing access_token")

    refresh_token = tokens.get("refresh_token") or previous.refresh_token
    expires_in = int(tokens.get("expires_in") or 3600)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    account_id = extract_account_id_from_access_token(access_token) or previous.account_id

    return OpenAICredentials(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        account_id=account_id,
        id_token=tokens.get("id_token") or previous.id_token,
        scope=tokens.get("scope") or previous.scope or settings.openai_oauth_scopes,
        token_type=tokens.get("token_type") or previous.token_type or "Bearer",
    )


def credentials_from_provider_settings(provider_settings: ProviderSettings) -> OpenAICredentials:
    try:
        data = decrypt(provider_settings.encrypted_credentials)
        return OpenAICredentials.model_validate_json(data)
    except ValidationError as e:
        raise OpenAIOAuthError(f"Invalid OpenAI credentials payload: {e}")


def save_credentials(
    provider_settings: ProviderSettings,
    repo: ProviderSettingsRepository,
    credentials: OpenAICredentials,
) -> ProviderSettings:
    updated_settings = ProviderSettings(
        user_email=provider_settings.user_email,
        provider_name=provider_settings.provider_name,
        encrypted_credentials=encrypt(credentials.model_dump_json()),
        auth_type="oauth",
    )
    return repo.save(updated_settings)


async def build_credentials_from_auth_code(code: str, code_verifier: str) -> OpenAICredentials:
    tokens = await exchange_code_for_tokens(code=code, code_verifier=code_verifier)
    return _build_credentials(tokens)


async def ensure_valid_openai_credentials(
    provider_settings: ProviderSettings,
    repo: ProviderSettingsRepository,
    refresh_buffer_seconds: int = 60,
) -> OpenAICredentials:
    credentials = credentials_from_provider_settings(provider_settings)

    if not credentials.refresh_token:
        if not credentials.access_token:
            raise OpenAIOAuthError("OpenAI credentials are missing access_token")
        return credentials

    if not credentials.is_expiring_soon(refresh_buffer_seconds=refresh_buffer_seconds):
        return credentials

    return await force_refresh_openai_credentials(
        provider_settings=provider_settings,
        repo=repo,
        current_credentials=credentials,
    )


async def force_refresh_openai_credentials(
    provider_settings: ProviderSettings,
    repo: ProviderSettingsRepository,
    current_credentials: Optional[OpenAICredentials] = None,
) -> OpenAICredentials:
    credentials = current_credentials or credentials_from_provider_settings(provider_settings)
    if not credentials.refresh_token:
        raise OpenAIOAuthError("OpenAI credentials are missing refresh_token")

    refreshed = await refresh_access_token(credentials.refresh_token)
    updated_credentials = _build_credentials(refreshed, previous=credentials)
    save_credentials(provider_settings, repo, updated_credentials)

    log.info("Refreshed OpenAI OAuth token for user %s", provider_settings.user_email)
    return updated_credentials


def is_openai_unauthorized_error(error: Exception) -> bool:
    msg = str(error).lower()
    return "401" in msg or "unauthorized" in msg
