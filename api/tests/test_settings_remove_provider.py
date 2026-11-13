"""Removing a provider's configuration puts it back to how it was before anyone set it up."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from src.crypto import encrypt
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from src.llm.providers import PROVIDERS
from tests.mock_data import TEST_USER_EMAIL, account_for

ANTHROPIC = {"api_key": "sk-ant-test"}
OPENAI_API = {"api_key": "sk-openai-test"}


@pytest.fixture(autouse=True)
def provider_listings(monkeypatch, without_bedrock):
    """Anthropic and the OpenAI API list one model each, without leaving the process."""
    models = SimpleNamespace(list=lambda: [SimpleNamespace(id="claude-sonnet-5-5", display_name="Claude Sonnet 5.5", capabilities=None)])
    monkeypatch.setattr("anthropic.Anthropic", lambda api_key: SimpleNamespace(models=models))

    def fake_get(url, headers=None, timeout=None):
        return httpx.Response(200, json={"data": [{"id": "gpt-5.5", "created": 1}]}, request=httpx.Request("GET", url))

    monkeypatch.setattr("src.llm.providers.openai_api.catalog.httpx.get", fake_get)


def _configure(test_client: TestClient, auth_headers: dict, provider: str, credentials: dict) -> None:
    assert test_client.post(f"/settings/providers/{provider}", json=credentials, headers=auth_headers).status_code == 201


def _remove(test_client: TestClient, auth_headers: dict, provider: str):
    return test_client.delete(f"/settings/providers/{provider}", headers=auth_headers)


def _configured(test_client: TestClient, auth_headers: dict) -> set[str]:
    providers = test_client.get("/settings/providers", headers=auth_headers).json()
    return {provider["provider_name"] for provider in providers if provider["is_configured"]}


def _agent_form_providers(test_client: TestClient, auth_headers: dict) -> list[str]:
    form = test_client.get("/agents/supported-models", headers=auth_headers).json()
    field = next(field for field in form["form_inputs"] if field["name"] == "agent_provider")
    return [option["value"] for option in field["options"]]


def test_a_removed_provider_is_not_configured_again(test_client: TestClient, auth_headers: dict):
    _configure(test_client, auth_headers, "Anthropic", ANTHROPIC)

    assert _remove(test_client, auth_headers, "Anthropic").status_code == 204

    assert "Anthropic" not in _configured(test_client, auth_headers)
    assert test_client.get("/settings/providers/Anthropic", headers=auth_headers).json() == {
        "provider_name": "Anthropic",
        "is_configured": False,
        "created_at": None,
        "updated_at": None,
    }


def test_agents_stop_being_offered_a_removed_provider(test_client: TestClient, auth_headers: dict):
    _configure(test_client, auth_headers, "Anthropic", ANTHROPIC)
    assert test_client.get("/llm/models/Anthropic", headers=auth_headers).json()[0]["model_id"] == "claude-sonnet-5-5"
    assert "Anthropic" in _agent_form_providers(test_client, auth_headers)

    _remove(test_client, auth_headers, "Anthropic")

    assert "Anthropic" not in _agent_form_providers(test_client, auth_headers)
    assert test_client.get("/llm/models/Anthropic", headers=auth_headers).json() == []


def test_removing_one_provider_leaves_the_others(test_client: TestClient, auth_headers: dict):
    _configure(test_client, auth_headers, "Anthropic", ANTHROPIC)
    _configure(test_client, auth_headers, "OpenAIAPI", OPENAI_API)

    _remove(test_client, auth_headers, "Anthropic")

    assert _configured(test_client, auth_headers) == {"OpenAIAPI"}
    assert _agent_form_providers(test_client, auth_headers) == ["OpenAIAPI"]


def test_a_removed_provider_can_be_set_up_again(test_client: TestClient, auth_headers: dict):
    _configure(test_client, auth_headers, "Anthropic", ANTHROPIC)
    _remove(test_client, auth_headers, "Anthropic")

    _configure(test_client, auth_headers, "Anthropic", {"api_key": "sk-ant-second"})

    assert "Anthropic" in _configured(test_client, auth_headers)


def test_removing_a_provider_that_was_never_set_up_is_fine(test_client: TestClient, auth_headers: dict):
    assert _remove(test_client, auth_headers, "Anthropic").status_code == 204


def test_an_unknown_provider_cannot_be_removed(test_client: TestClient, auth_headers: dict):
    assert _remove(test_client, auth_headers, "NotAProvider").status_code == 400


@pytest.mark.parametrize("provider", [p.name for p in PROVIDERS])
def test_every_provider_the_settings_page_lists_can_be_removed(test_client: TestClient, auth_headers: dict, provider: str):
    # Stored directly: OpenAI is connected by signing in, so its credentials can't be posted like a key.
    ProviderSettingsRepository().save(
        ProviderSettings(account_id=account_for(TEST_USER_EMAIL), provider_name=provider, encrypted_credentials=encrypt("{}"))
    )
    assert provider in _configured(test_client, auth_headers)

    assert _remove(test_client, auth_headers, provider).status_code == 204

    assert provider not in _configured(test_client, auth_headers)
