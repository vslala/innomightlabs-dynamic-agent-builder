"""Provider credential loading for LLM-backed features."""

from __future__ import annotations

import json
from typing import Any, cast

from src.auth.openai_oauth import ensure_valid_openai_credentials
from src.crypto import decrypt
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository


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
    return cast(dict[str, Any], raw_credentials)
