"""Ollama wiring: provider settings and model discovery."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from src.crypto import encrypt
from src.llm.providers.ollama.catalog import OllamaCatalog
from src.settings.models import ProviderSettings
from tests.mock_data import account_for, TEST_USER_EMAIL

ENDPOINT_URL = "http://ollama.test:11434"


def _provider_settings(**credentials) -> ProviderSettings:
    return ProviderSettings(
        account_id=account_for(TEST_USER_EMAIL),
        provider_name="Ollama",
        encrypted_credentials=encrypt(json.dumps(credentials)),
    )


def _tags_response(monkeypatch, payload, status_code: int = 200) -> list[httpx.Request]:
    """Stub `/api/tags`, returning the requests it received."""
    seen: list[httpx.Request] = []

    def fake_get(url, headers=None, timeout=None):
        request = httpx.Request("GET", url, headers=headers)
        seen.append(request)
        return httpx.Response(status_code, json=payload, request=request)

    monkeypatch.setattr("src.llm.providers.ollama.catalog.httpx.get", fake_get)
    return seen


class TestOllamaModelDiscovery:
    def test_lists_pulled_models_from_the_configured_endpoint(self, monkeypatch):
        seen = _tags_response(
            monkeypatch,
            {"models": [{"name": "llama3.1:8b"}, {"name": "qwen3:4b"}]},
        )

        models = OllamaCatalog().list_models(_provider_settings(endpoint_url=ENDPOINT_URL))

        assert [model.model_name for model in models] == ["llama3.1:8b", "qwen3:4b"]
        assert [model.display_name for model in models] == ["[Ollama] llama3.1:8b", "[Ollama] qwen3:4b"]
        assert {model.provider for model in models} == {"ollama"}
        assert str(seen[0].url) == f"{ENDPOINT_URL}/api/tags"

    def test_forwards_bearer_auth_when_configured(self, monkeypatch):
        seen = _tags_response(monkeypatch, {"models": []})

        OllamaCatalog().list_models(_provider_settings(endpoint_url=ENDPOINT_URL, api_key="secret"))

        assert seen[0].headers["Authorization"] == "Bearer secret"

    def test_unreachable_endpoint_yields_no_models_rather_than_raising(self, monkeypatch):
        def refuse(url, headers=None, timeout=None):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr("src.llm.providers.ollama.catalog.httpx.get", refuse)

        assert OllamaCatalog().list_models(_provider_settings(endpoint_url=ENDPOINT_URL)) == []

    def test_auth_failure_yields_no_models(self, monkeypatch):
        _tags_response(monkeypatch, {"error": "unauthorized"}, status_code=401)

        assert OllamaCatalog().list_models(_provider_settings(endpoint_url=ENDPOINT_URL)) == []

    @pytest.mark.parametrize(
        "payload",
        [{}, {"models": "not-a-list"}, {"models": [{}, "junk", {"name": "   "}]}],
    )
    def test_unexpected_payloads_yield_no_models(self, monkeypatch, payload):
        _tags_response(monkeypatch, payload)

        assert OllamaCatalog().list_models(_provider_settings(endpoint_url=ENDPOINT_URL)) == []

    def test_a_misconfigured_endpoint_yields_no_models(self, monkeypatch):
        _tags_response(monkeypatch, {"models": [{"name": "llama3.1:8b"}]})

        assert OllamaCatalog().list_models(_provider_settings(endpoint_url="not-a-url")) == []


class TestOllamaProviderSettingsRouter:
    def test_ollama_is_an_offered_provider(self, test_client: TestClient, auth_headers: dict):
        response = test_client.get("/settings/providers", headers=auth_headers)

        assert response.status_code == 200
        ollama = next(p for p in response.json() if p["provider_name"] == "Ollama")
        assert [field["name"] for field in ollama["form"]["form_inputs"]] == ["endpoint_url", "api_key"]
        assert ollama["is_configured"] is False

    def test_saves_a_plain_local_endpoint_without_an_api_key(
        self, test_client: TestClient, auth_headers: dict
    ):
        response = test_client.post(
            "/settings/providers/Ollama",
            json={"endpoint_url": "http://localhost:11434", "api_key": ""},
            headers=auth_headers,
        )

        assert response.status_code == 201
        assert response.json()["is_configured"] is True

    def test_saves_an_authenticated_remote_endpoint(self, test_client: TestClient, auth_headers: dict):
        response = test_client.post(
            "/settings/providers/Ollama",
            json={"endpoint_url": "https://ollama.example.com", "api_key": "secret-token"},
            headers=auth_headers,
        )

        assert response.status_code == 201

    def test_credentials_are_never_echoed_back(self, test_client: TestClient, auth_headers: dict):
        test_client.post(
            "/settings/providers/Ollama",
            json={"endpoint_url": ENDPOINT_URL, "api_key": "secret-token"},
            headers=auth_headers,
        )

        response = test_client.get("/settings/providers/Ollama", headers=auth_headers)

        assert response.status_code == 200
        assert "secret-token" not in response.text
        assert response.json()["is_configured"] is True

    def test_endpoint_url_remains_required(self, test_client: TestClient, auth_headers: dict):
        response = test_client.post(
            "/settings/providers/Ollama",
            json={"api_key": "secret-token"},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "endpoint_url" in response.json()["detail"]

    def test_required_fields_are_still_enforced_for_other_providers(
        self, test_client: TestClient, auth_headers: dict
    ):
        response = test_client.post(
            "/settings/providers/Bedrock",
            json={"access_key": "key", "secret_key": ""},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "secret_key" in response.json()["detail"]
