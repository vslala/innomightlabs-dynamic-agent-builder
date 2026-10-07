"""OpenAI model discovery from the Codex backend's model catalog."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from src.auth.openai_oauth import OpenAICredentials
from src.config.settings import DEFAULT_OPENAI_MODELS
from src.crypto import encrypt
from src.llm import models as llm_models
from src.llm.models import ModelsService
from src.settings.models import ProviderSettings
from tests.mock_data import TEST_USER_EMAIL

CATALOG = {
    "models": [
        {"slug": "gpt-6-luna", "display_name": "GPT-6-Luna", "visibility": "list", "supported_in_api": True, "priority": 4},
        {"slug": "gpt-6-astra", "display_name": "GPT-6-Astra", "visibility": "list", "supported_in_api": True, "priority": 2},
        {"slug": "gpt-reserve", "display_name": "GPT-Reserve", "visibility": "hide", "supported_in_api": True, "priority": 4},
        {"slug": "gpt-chat-only", "display_name": "Chat only", "visibility": "list", "supported_in_api": False, "priority": 1},
        {"slug": "gpt-5.6-sol", "visibility": "list", "supported_in_api": True},
    ]
}


@pytest.fixture(autouse=True)
def configured_models(monkeypatch):
    """Deploy scripts set OPENAI_MODELS; pin the fallback so these tests don't depend on the shell."""
    monkeypatch.setattr(llm_models.settings, "openai_models", DEFAULT_OPENAI_MODELS.copy())


def _provider_settings(account_id: str | None = "acct-1") -> ProviderSettings:
    credentials = OpenAICredentials(
        access_token="access-token",
        refresh_token="refresh-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        account_id=account_id,
    )
    return ProviderSettings(
        user_email=TEST_USER_EMAIL,
        provider_name="OpenAI",
        encrypted_credentials=encrypt(credentials.model_dump_json()),
        auth_type="oauth",
    )


def _catalog_response(monkeypatch, payload=CATALOG, status_code: int = 200) -> list[httpx.Request]:
    """Stub the catalog request, returning the requests it received."""
    seen: list[httpx.Request] = []

    def fake_get(url, params=None, headers=None, timeout=None):
        request = httpx.Request("GET", url, params=params, headers=headers)
        seen.append(request)
        return httpx.Response(status_code, json=payload, request=request)

    monkeypatch.setattr("src.llm.models.httpx.get", fake_get)
    return seen


def test_lists_the_catalogs_listed_models_in_priority_order(monkeypatch):
    seen = _catalog_response(monkeypatch)

    models = ModelsService().get_openai_models(_provider_settings())

    assert [model.model_name for model in models] == ["gpt-6-astra", "gpt-6-luna", "gpt-5.6-sol"]
    assert [model.display_name for model in models] == [
        "[OpenAI] GPT-6-Astra",
        "[OpenAI] GPT-6-Luna",
        "[OpenAI] gpt-5.6-sol",
    ]
    assert all(model.provider == "openai" for model in models)
    [request] = seen
    assert str(request.url).startswith("https://chatgpt.com/backend-api/codex/models?client_version=")
    assert request.headers["Authorization"] == "Bearer access-token"
    assert request.headers["ChatGPT-Account-ID"] == "acct-1"


def test_reuses_an_accounts_catalog_until_it_expires(monkeypatch):
    seen = _catalog_response(monkeypatch)
    service = ModelsService()

    service.get_openai_models(_provider_settings())
    service.get_openai_models(_provider_settings())
    assert len(seen) == 1

    monkeypatch.setattr(llm_models.time, "monotonic", lambda: 10**12)
    service.get_openai_models(_provider_settings())
    assert len(seen) == 2


@pytest.mark.parametrize(
    ("payload", "status_code"),
    [
        ({"error": "expired"}, 401),
        ({"unexpected": True}, 200),
        ({"models": [{"slug": "gpt-hidden", "visibility": "hide"}]}, 200),
    ],
)
def test_falls_back_to_the_configured_models(monkeypatch, payload, status_code):
    _catalog_response(monkeypatch, payload, status_code)

    models = ModelsService().get_openai_models(_provider_settings())

    assert [model.model_name for model in models] == DEFAULT_OPENAI_MODELS


def test_unreadable_credentials_fall_back_without_a_request(monkeypatch):
    seen = _catalog_response(monkeypatch)
    broken = ProviderSettings(
        user_email=TEST_USER_EMAIL,
        provider_name="OpenAI",
        encrypted_credentials="not-encrypted",
        auth_type="oauth",
    )

    models = ModelsService().get_openai_models(broken)

    assert [model.model_name for model in models] == DEFAULT_OPENAI_MODELS
    assert seen == []
