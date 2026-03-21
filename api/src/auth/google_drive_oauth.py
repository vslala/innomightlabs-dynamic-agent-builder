from __future__ import annotations

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

GOOGLE_DRIVE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_DRIVE_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleDriveOAuthError(Exception):
    """Raised when Google Drive OAuth operations fail."""


class GoogleDriveCredentials(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: datetime
    scope: str = ""
    token_type: str = "Bearer"

    def is_expiring_soon(self, refresh_buffer_seconds: int = 60) -> bool:
        now = datetime.now(timezone.utc)
        return (self.expires_at - now).total_seconds() <= refresh_buffer_seconds


class GoogleDriveOAuthState(BaseModel):
    nonce: str
    user_email: str
    agent_id: str
    skill_id: str
    return_to: str
    expires_at: int

    def is_expired(self) -> bool:
        now_ts = int(datetime.now(timezone.utc).timestamp())
        return now_ts > self.expires_at


def build_authorization_url(state: str) -> str:
    if not settings.is_google_drive_oauth_configured():
        raise GoogleDriveOAuthError("Google Drive OAuth is not configured")

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_drive_redirect_uri,
        "response_type": "code",
        "scope": settings.google_drive_oauth_scopes,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_DRIVE_AUTHORIZE_URL}?{urlencode(params)}"


def encode_state_session(session: GoogleDriveOAuthState) -> str:
    return encrypt(session.model_dump_json())


def decode_state_session(state: str | None) -> Optional[GoogleDriveOAuthState]:
    if not state:
        return None

    try:
        decoded = decrypt(state)
        return GoogleDriveOAuthState.model_validate_json(decoded)
    except (ValidationError, Exception):
        return None


def create_state_session(*, user_email: str, agent_id: str, skill_id: str, return_to: str, ttl_seconds: int) -> GoogleDriveOAuthState:
    now_ts = int(datetime.now(timezone.utc).timestamp())
    return GoogleDriveOAuthState(
        nonce=secrets.token_urlsafe(32),
        user_email=user_email,
        agent_id=agent_id,
        skill_id=skill_id,
        return_to=return_to,
        expires_at=now_ts + ttl_seconds,
    )


async def exchange_code_for_tokens(code: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            GOOGLE_DRIVE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.google_drive_redirect_uri,
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    if not response.is_success:
        raise GoogleDriveOAuthError(f"Google Drive token exchange failed: {response.text}")

    payload = response.json()
    return payload if isinstance(payload, dict) else {}


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            GOOGLE_DRIVE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    if not response.is_success:
        raise GoogleDriveOAuthError(f"Google Drive token refresh failed: {response.text}")

    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _build_credentials(
    tokens: dict[str, Any],
    previous: Optional[GoogleDriveCredentials] = None,
) -> GoogleDriveCredentials:
    previous = previous or GoogleDriveCredentials(
        access_token="",
        refresh_token=None,
        expires_at=datetime.now(timezone.utc),
        scope=settings.google_drive_oauth_scopes,
        token_type="Bearer",
    )

    access_token = tokens.get("access_token") or previous.access_token
    if not access_token:
        raise GoogleDriveOAuthError("Google Drive token response missing access_token")

    refresh_token = tokens.get("refresh_token") or previous.refresh_token
    expires_in = int(tokens.get("expires_in") or 3600)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    return GoogleDriveCredentials(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        scope=tokens.get("scope") or previous.scope or settings.google_drive_oauth_scopes,
        token_type=tokens.get("token_type") or previous.token_type or "Bearer",
    )


def credentials_from_provider_settings(provider_settings: ProviderSettings) -> GoogleDriveCredentials:
    try:
        data = decrypt(provider_settings.encrypted_credentials)
        return GoogleDriveCredentials.model_validate_json(data)
    except ValidationError as e:
        raise GoogleDriveOAuthError(f"Invalid Google Drive credentials payload: {e}")


def save_credentials(
    provider_settings: ProviderSettings,
    repo: ProviderSettingsRepository,
    credentials: GoogleDriveCredentials,
) -> ProviderSettings:
    updated_settings = ProviderSettings(
        user_email=provider_settings.user_email,
        provider_name=provider_settings.provider_name,
        encrypted_credentials=encrypt(credentials.model_dump_json()),
        auth_type="oauth",
    )
    return repo.save(updated_settings)


async def build_credentials_from_auth_code(code: str) -> GoogleDriveCredentials:
    tokens = await exchange_code_for_tokens(code)
    return _build_credentials(tokens)


async def ensure_valid_google_drive_credentials(
    provider_settings: ProviderSettings,
    repo: ProviderSettingsRepository,
    refresh_buffer_seconds: int = 60,
) -> GoogleDriveCredentials:
    credentials = credentials_from_provider_settings(provider_settings)

    if not credentials.refresh_token:
        if not credentials.access_token:
            raise GoogleDriveOAuthError("Google Drive credentials are missing access_token")
        return credentials

    if not credentials.is_expiring_soon(refresh_buffer_seconds=refresh_buffer_seconds):
        return credentials

    return await force_refresh_google_drive_credentials(
        provider_settings=provider_settings,
        repo=repo,
        current_credentials=credentials,
    )


async def force_refresh_google_drive_credentials(
    provider_settings: ProviderSettings,
    repo: ProviderSettingsRepository,
    current_credentials: Optional[GoogleDriveCredentials] = None,
) -> GoogleDriveCredentials:
    credentials = current_credentials or credentials_from_provider_settings(provider_settings)
    if not credentials.refresh_token:
        raise GoogleDriveOAuthError("Google Drive credentials are missing refresh_token")

    refreshed = await refresh_access_token(credentials.refresh_token)
    updated_credentials = _build_credentials(refreshed, previous=credentials)
    save_credentials(provider_settings, repo, updated_credentials)
    return updated_credentials
