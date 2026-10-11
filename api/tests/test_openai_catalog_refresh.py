"""The OpenAI model catalog uses the same token refresh chat does, so an expired sign-in doesn't shrink the list."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from src.auth.openai_oauth import OpenAICredentials, OpenAIOAuthError, credentials_from_provider_settings
from src.config.settings import DEFAULT_OPENAI_MODELS
from src.crypto import encrypt
from src.llm import models as llm_models
from src.llm.models import ModelsService
from src.settings.models import ProviderSettings
from tests.mock_data import account_for, TEST_USER_EMAIL

CATALOG = {"models": [{"slug": "gpt-6-astra", "display_name": "GPT-6-Astra", "visibility": "list", "priority": 1}]}


@pytest.fixture(autouse=True)
def configured_models(monkeypatch):
    monkeypatch.setattr(llm_models.settings, "openai_models", DEFAULT_OPENAI_MODELS.copy())
    monkeypatch.setattr("src.auth.openai_oauth.settings.openai_oauth_client_id", "client-1")


class FakeRepository:
    def __init__(self):
        self.saved: list[ProviderSettings] = []

    def save(self, provider_settings: ProviderSettings) -> ProviderSettings:
        self.saved.append(provider_settings)
        return provider_settings


@pytest.fixture
def repository(monkeypatch) -> FakeRepository:
    repo = FakeRepository()
    monkeypatch.setattr("src.settings.repository.get_provider_settings_repository", lambda: repo)
    return repo


def _signed_in(expires_in: timedelta, refresh_token: str | None = "refresh-1") -> ProviderSettings:
    credentials = OpenAICredentials(
        access_token="old-token",
        refresh_token=refresh_token,
        expires_at=datetime.now(timezone.utc) + expires_in,
        account_id="acct-1",
    )
    return ProviderSettings(
        account_id=account_for(TEST_USER_EMAIL),
        provider_name="OpenAI",
        encrypted_credentials=encrypt(credentials.model_dump_json()),
        auth_type="oauth",
    )


def _catalog_requests(monkeypatch) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def fake_get(url, params=None, headers=None, timeout=None):
        request = httpx.Request("GET", url, params=params, headers=headers)
        seen.append(request)
        status = 200 if headers["Authorization"] == "Bearer new-token" else 401
        return httpx.Response(status, json=CATALOG, request=request)

    monkeypatch.setattr("src.llm.models.httpx.get", fake_get)
    return seen


def _refresh_gives(monkeypatch, tokens: dict | Exception) -> list[str]:
    asked: list[str] = []

    async def fake_refresh(refresh_token: str) -> dict:
        asked.append(refresh_token)
        if isinstance(tokens, Exception):
            raise tokens
        return tokens

    monkeypatch.setattr("src.auth.openai_oauth.refresh_access_token", fake_refresh)
    return asked


def test_an_expired_token_is_refreshed_and_saved_before_the_catalog_is_read(monkeypatch, repository):
    seen = _catalog_requests(monkeypatch)
    asked = _refresh_gives(monkeypatch, {"access_token": "new-token", "expires_in": 864000})

    models = ModelsService().get_openai_models(_signed_in(timedelta(minutes=-5)))

    assert [model.model_name for model in models] == ["gpt-6-astra"]
    assert asked == ["refresh-1"]
    assert [request.headers["Authorization"] for request in seen] == ["Bearer new-token"]
    [saved] = repository.saved
    assert (saved.account_id, saved.provider_name) == (account_for(TEST_USER_EMAIL), "OpenAI")
    stored = credentials_from_provider_settings(saved)
    assert stored.access_token == "new-token"
    assert stored.refresh_token == "refresh-1"


def test_a_live_token_is_used_as_it_is(monkeypatch, repository):
    seen = _catalog_requests(monkeypatch)
    asked = _refresh_gives(monkeypatch, {"access_token": "new-token"})
    settings = _signed_in(timedelta(days=3))

    ModelsService().get_openai_models(settings)

    assert asked == []
    assert repository.saved == []
    assert seen[0].headers["Authorization"] == "Bearer old-token"


def test_a_cached_catalog_needs_neither_a_refresh_nor_a_request(monkeypatch, repository):
    seen = _catalog_requests(monkeypatch)
    asked = _refresh_gives(monkeypatch, {"access_token": "new-token"})
    service = ModelsService()
    service.get_openai_models(_signed_in(timedelta(minutes=-5)))

    service.get_openai_models(_signed_in(timedelta(minutes=-5)))

    assert len(seen) == 1
    assert len(asked) == 1


def test_a_refused_refresh_offers_the_configured_models_and_says_why(monkeypatch, repository, caplog):
    _catalog_requests(monkeypatch)
    _refresh_gives(monkeypatch, OpenAIOAuthError("Your OpenAI sign-in has expired. Please connect it again."))

    models = ModelsService().get_openai_models(_signed_in(timedelta(minutes=-5)))

    assert [model.model_name for model in models] == DEFAULT_OPENAI_MODELS
    assert repository.saved == []
    assert "sign-in has expired" in caplog.text


async def test_refreshes_from_inside_a_running_event_loop(monkeypatch, repository):
    """Form options are built by sync code that async routes call, so a loop is already running."""
    _catalog_requests(monkeypatch)
    _refresh_gives(monkeypatch, {"access_token": "new-token"})

    models = ModelsService().get_openai_models(_signed_in(timedelta(minutes=-5)))

    assert [model.model_name for model in models] == ["gpt-6-astra"]
