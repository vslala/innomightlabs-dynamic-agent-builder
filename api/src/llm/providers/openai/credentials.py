"""A ChatGPT sign-in's credentials: an OAuth token that lasts about ten days, refreshed and saved when it has expired.

Whatever uses the token goes through here, so an expired one is refreshed rather than sent as is."""

from __future__ import annotations

from typing import Any, cast

from src.auth.openai_oauth import OpenAICredentials, ensure_valid_openai_credentials
from src.common.blocking import run_blocking
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository


class OpenAISignInCredentials:
    async def load(
        self, provider_settings: ProviderSettings, provider_settings_repo: ProviderSettingsRepository
    ) -> dict[str, Any]:
        credentials = await ensure_valid_openai_credentials(provider_settings, provider_settings_repo)
        return cast(dict[str, Any], credentials.model_dump(mode="json"))


def load_openai_credentials_blocking(
    provider_settings: ProviderSettings, provider_settings_repo: ProviderSettingsRepository
) -> OpenAICredentials:
    """The same refresh, for sync callers such as the model catalog."""
    return run_blocking(ensure_valid_openai_credentials(provider_settings, provider_settings_repo))
