import json
from datetime import datetime, timezone

import pytest

from src.auth.openai_oauth import OpenAICredentials
from src.crypto import encrypt
from src.llm.credentials import load_provider_credentials
from src.settings.models import ProviderSettings


class FakeProviderSettingsRepository:
    pass


async def test_load_provider_credentials_decrypts_static_provider_credentials():
    provider_settings = ProviderSettings(
        user_email="owner@example.com",
        provider_name="Bedrock",
        encrypted_credentials=encrypt(json.dumps({"api_key": "secret"})),
    )

    credentials = await load_provider_credentials(
        provider_name="Bedrock",
        provider_settings=provider_settings,
        provider_settings_repo=FakeProviderSettingsRepository(),
    )

    assert credentials == {"api_key": "secret"}


async def test_load_provider_credentials_uses_openai_oauth_refresh_path(monkeypatch):
    provider_settings = ProviderSettings(
        user_email="owner@example.com",
        provider_name="OpenAI",
        encrypted_credentials="encrypted",
        auth_type="oauth",
    )
    expected = OpenAICredentials(
        access_token="access-token",
        refresh_token="refresh-token",
        expires_at=datetime.now(timezone.utc),
        account_id="account-1",
    )
    seen = {}

    async def fake_ensure_valid_openai_credentials(settings, repo):
        seen["settings"] = settings
        seen["repo"] = repo
        return expected

    monkeypatch.setattr(
        "src.llm.credentials.ensure_valid_openai_credentials",
        fake_ensure_valid_openai_credentials,
    )
    repo = FakeProviderSettingsRepository()

    credentials = await load_provider_credentials(
        provider_name="OpenAI",
        provider_settings=provider_settings,
        provider_settings_repo=repo,
    )

    assert seen == {"settings": provider_settings, "repo": repo}
    assert credentials["access_token"] == "access-token"
    assert credentials["account_id"] == "account-1"


async def test_load_provider_credentials_rejects_non_object_static_credentials():
    provider_settings = ProviderSettings(
        user_email="owner@example.com",
        provider_name="Bedrock",
        encrypted_credentials=encrypt(json.dumps(["not", "an", "object"])),
    )

    with pytest.raises(ValueError, match="credentials must be a JSON object"):
        await load_provider_credentials(
            provider_name="Bedrock",
            provider_settings=provider_settings,
            provider_settings_repo=FakeProviderSettingsRepository(),
        )
