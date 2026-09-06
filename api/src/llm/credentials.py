"""Provider credential loading for LLM-backed features."""

from __future__ import annotations

import json
from typing import Any, cast

import httpx

from src.auth.openai_oauth import ensure_valid_openai_credentials
from src.config import settings
from src.crypto import decrypt
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from src.settings.schemas import ANTHROPIC_OAUTH_PROVIDER


ANTHROPIC_OAUTH_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
ANTHROPIC_OAUTH_BETA = "oauth-2025-04-20"


async def mint_anthropic_oauth_access_token(credentials: dict[str, Any]) -> dict[str, Any]:
    """Exchange an Anthropic refresh token for a short-lived access token."""
    refresh_token = credentials.get("refresh_token")
    client_id = credentials.get("client_id")
    if not refresh_token or not client_id:
        raise ValueError("Missing required Anthropic OAuth credentials: 'refresh_token' and 'client_id'")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                ANTHROPIC_OAUTH_TOKEN_URL,
                headers={
                    "Content-Type": "application/json",
                    "anthropic-beta": ANTHROPIC_OAUTH_BETA,
                },
                json={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                },
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise ValueError("Unable to refresh Anthropic OAuth access token") from exc

    access_token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(access_token, str) or not access_token:
        raise ValueError("Anthropic OAuth token response did not include an access token")
    return {"access_token": access_token}


async def load_provider_credentials(
    *,
    provider_name: str,
    provider_settings: ProviderSettings,
    provider_settings_repo: ProviderSettingsRepository,
) -> dict[str, Any]:
    """Load provider credentials, including provider-specific refresh behavior."""
    if provider_name == "OpenAI":
        credentials = await ensure_valid_openai_credentials(
            provider_settings,
            provider_settings_repo,
        )
        return cast(dict[str, Any], credentials.model_dump(mode="json"))

    raw_credentials = json.loads(decrypt(provider_settings.encrypted_credentials))
    if not isinstance(raw_credentials, dict):
        raise ValueError(f"Provider '{provider_name}' credentials must be a JSON object")

    if provider_name == ANTHROPIC_OAUTH_PROVIDER:
        if not settings.anthropic_oauth_shortcircuit_enabled:
            raise ValueError("Anthropic OAuth short-circuit provider is disabled")
        return await mint_anthropic_oauth_access_token(cast(dict[str, Any], raw_credentials))

    return cast(dict[str, Any], raw_credentials)
