from __future__ import annotations

from fastapi.testclient import TestClient

from src.config import settings
from src.settings.schemas import ANTHROPIC_OAUTH_PROVIDER


def test_anthropic_oauth_provider_is_hidden_when_feature_flag_is_disabled(
    test_client: TestClient,
    auth_headers: dict,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "anthropic_oauth_shortcircuit_enabled", False)

    response = test_client.get("/settings/providers", headers=auth_headers)

    assert response.status_code == 200
    assert ANTHROPIC_OAUTH_PROVIDER not in {
        provider["provider_name"] for provider in response.json()
    }


def test_anthropic_oauth_provider_is_available_when_feature_flag_is_enabled(
    test_client: TestClient,
    auth_headers: dict,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "anthropic_oauth_shortcircuit_enabled", True)

    response = test_client.get("/settings/providers", headers=auth_headers)

    assert response.status_code == 200
    provider = next(
        provider
        for provider in response.json()
        if provider["provider_name"] == ANTHROPIC_OAUTH_PROVIDER
    )
    assert provider["form"]["form_name"] == "Anthropic OAuth Configuration"
    assert [field["name"] for field in provider["form"]["form_inputs"]] == [
        "refresh_token",
        "client_id",
    ]
