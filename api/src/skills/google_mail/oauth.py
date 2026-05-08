from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ValidationError

from src.config import settings
from src.crypto import decrypt, encrypt
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from src.skills.google_mail.models import GoogleMailCredentials

GOOGLE_MAIL_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_MAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleMailOAuthError(Exception):
    """Raised when Google Mail OAuth operations fail."""


class GoogleMailOAuthState(BaseModel):
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
    if not settings.is_google_mail_oauth_configured():
        raise GoogleMailOAuthError("Google Mail OAuth is not configured")

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_mail_redirect_uri,
        "response_type": "code",
        "scope": settings.google_mail_oauth_scopes,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_MAIL_AUTHORIZE_URL}?{urlencode(params)}"


def encode_state_session(session: GoogleMailOAuthState) -> str:
    return encrypt(session.model_dump_json())


def decode_state_session(state: str | None) -> Optional[GoogleMailOAuthState]:
    if not state:
        return None

    try:
        decoded = decrypt(state)
        return GoogleMailOAuthState.model_validate_json(decoded)
    except (ValidationError, Exception):
        return None


def create_state_session(*, user_email: str, agent_id: str, skill_id: str, return_to: str, ttl_seconds: int) -> GoogleMailOAuthState:
    now_ts = int(datetime.now(timezone.utc).timestamp())
    return GoogleMailOAuthState(
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
            GOOGLE_MAIL_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.google_mail_redirect_uri,
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    if not response.is_success:
        raise GoogleMailOAuthError(f"Google Mail token exchange failed: {response.text}")

    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _build_credentials(tokens: dict[str, Any]) -> GoogleMailCredentials:
    access_token = str(tokens.get("access_token") or "").strip()
    if not access_token:
        raise GoogleMailOAuthError("Google Mail token response missing access_token")

    return GoogleMailCredentials(
        access_token=access_token,
        refresh_token=tokens.get("refresh_token"),
        scope=tokens.get("scope") or settings.google_mail_oauth_scopes,
        token_type=tokens.get("token_type") or "Bearer",
    ).with_token_response(tokens)


async def build_credentials_from_auth_code(code: str) -> GoogleMailCredentials:
    tokens = await exchange_code_for_tokens(code)
    return _build_credentials(tokens)


def save_credentials(
    provider_settings: ProviderSettings,
    repo: ProviderSettingsRepository,
    credentials: GoogleMailCredentials,
) -> ProviderSettings:
    updated_settings = ProviderSettings(
        user_email=provider_settings.user_email,
        provider_name=provider_settings.provider_name,
        encrypted_credentials=encrypt(credentials.model_dump_json()),
        auth_type="oauth",
    )
    return repo.save(updated_settings)
