"""Google Ads OAuth, on the platform's Google client, in the same shape as Gmail and Drive.

OAuth is the only credential: no developer token is requested or sent.
"""

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
from src.skills.google_ads.models import GoogleAdsCredentials

GOOGLE_ADS_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_ADS_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleAdsOAuthError(Exception):
    """Raised when Google Ads OAuth operations fail."""


class GoogleAdsOAuthState(BaseModel):
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
    if not settings.is_google_ads_oauth_configured():
        raise GoogleAdsOAuthError("Google Ads OAuth is not configured")

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_ads_redirect_uri,
        "response_type": "code",
        "scope": settings.google_ads_oauth_scopes,
        # Google returns a refresh token only for offline access, and only on a fresh consent.
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_ADS_AUTHORIZE_URL}?{urlencode(params)}"


def encode_state_session(session: GoogleAdsOAuthState) -> str:
    return encrypt(session.model_dump_json())


def decode_state_session(state: str | None) -> Optional[GoogleAdsOAuthState]:
    if not state:
        return None

    try:
        decoded = decrypt(state)
        return GoogleAdsOAuthState.model_validate_json(decoded)
    except (ValidationError, Exception):
        return None


def create_state_session(
    *, user_email: str, agent_id: str, skill_id: str, return_to: str, ttl_seconds: int
) -> GoogleAdsOAuthState:
    now_ts = int(datetime.now(timezone.utc).timestamp())
    return GoogleAdsOAuthState(
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
            GOOGLE_ADS_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.google_ads_redirect_uri,
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    if not response.is_success:
        raise GoogleAdsOAuthError(f"Google Ads token exchange failed: {response.text[:500]}")

    payload = response.json()
    return payload if isinstance(payload, dict) else {}


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            GOOGLE_ADS_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    if not response.is_success:
        raise GoogleAdsOAuthError(f"Google Ads token refresh failed: {response.text[:500]}")

    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _build_credentials(tokens: dict[str, Any]) -> GoogleAdsCredentials:
    access_token = str(tokens.get("access_token") or "").strip()
    if not access_token:
        raise GoogleAdsOAuthError("Google Ads token response missing access_token")

    return GoogleAdsCredentials(
        access_token=access_token,
        refresh_token=tokens.get("refresh_token"),
        scope=tokens.get("scope") or settings.google_ads_oauth_scopes,
        token_type=tokens.get("token_type") or "Bearer",
    ).with_token_response(tokens)


async def build_credentials_from_auth_code(code: str) -> GoogleAdsCredentials:
    tokens = await exchange_code_for_tokens(code)
    return _build_credentials(tokens)


def save_credentials(
    provider_settings: ProviderSettings,
    repo: ProviderSettingsRepository,
    credentials: GoogleAdsCredentials,
) -> ProviderSettings:
    updated_settings = ProviderSettings(
        user_email=provider_settings.user_email,
        provider_name=provider_settings.provider_name,
        encrypted_credentials=encrypt(credentials.model_dump_json()),
        auth_type="oauth",
    )
    return repo.save(updated_settings)
