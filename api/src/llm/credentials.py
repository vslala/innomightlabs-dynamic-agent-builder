"""Loading a provider's credentials for LLM-backed features: each provider says how (`Provider.credentials`)."""

from __future__ import annotations

from typing import Any

from src.llm.providers import provider
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository


async def load_provider_credentials(
    *,
    provider_name: str,
    provider_settings: ProviderSettings,
    provider_settings_repo: ProviderSettingsRepository,
) -> dict[str, Any]:
    """The credentials a provider's chat client and image adapter are given, refreshed first where they expire."""
    return await provider(provider_name).credentials.load(provider_settings, provider_settings_repo)
