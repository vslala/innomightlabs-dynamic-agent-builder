import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from src.crypto import encrypt
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from tests.mock_data import account_for, TEST_USER_EMAIL


def test_list_connectors_reports_status(test_client, auth_headers, dynamodb_table):
    response = test_client.get("/connectors", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    gmail = next(item for item in payload if item["connector_id"] == "google_mail")
    assert gmail["connected"] is False
    assert gmail["connect_path"] == "/connectors/google_mail/start"

    ProviderSettingsRepository().save(
        ProviderSettings(
            account_id=account_for(TEST_USER_EMAIL),
            provider_name="GoogleMail",
            encrypted_credentials="encrypted",
            auth_type="oauth",
        )
    )

    response = test_client.get("/connectors", headers=auth_headers)
    gmail = next(item for item in response.json() if item["connector_id"] == "google_mail")
    assert gmail["connected"] is True


def test_start_connector_oauth_does_not_require_agent(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("src.config.settings.is_google_mail_oauth_configured", lambda: True)

    response = test_client.post(
        "/connectors/google_mail/start",
        headers=auth_headers,
        json={"return_to": "http://localhost:5173/dashboard/connectors"},
    )

    assert response.status_code == 200
    authorize_url = response.json()["authorize_url"]
    params = parse_qs(urlparse(authorize_url).query)
    assert params["client_id"]
    assert params["state"]


def connect(connector_provider: str, credentials: dict) -> None:
    ProviderSettingsRepository().save(ProviderSettings(
        account_id=account_for(TEST_USER_EMAIL), provider_name=connector_provider,
        encrypted_credentials=encrypt(json.dumps(credentials)), auth_type="oauth",
    ))


def is_connected(test_client, auth_headers, connector_id: str) -> bool:
    listed = test_client.get("/connectors", headers=auth_headers).json()
    return next(item for item in listed if item["connector_id"] == connector_id)["connected"]


@pytest.fixture
def google_revoke(monkeypatch):
    """Google's revoke endpoint: the tokens it was asked to revoke, and the status it answers with."""
    revoked: list[str] = []
    answer = {"status": 200}

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://oauth2.googleapis.com/revoke"
        revoked.append(parse_qs(request.content.decode())["token"][0])
        return httpx.Response(answer["status"])

    real = httpx.AsyncClient
    monkeypatch.setattr("src.connectors.service.httpx.AsyncClient",
                        lambda **kwargs: real(**{**kwargs, "transport": httpx.MockTransport(handler)}))
    return revoked, answer


@pytest.mark.parametrize(("connector_id", "provider"), [
    ("google_mail", "GoogleMail"), ("google_drive", "GoogleDrive"), ("google_ads", "GoogleAds"),
])
def test_disconnecting_revokes_the_refresh_token_and_forgets_the_connection(
    test_client, auth_headers, dynamodb_table, google_revoke, connector_id, provider,
):
    revoked, _ = google_revoke
    connect(provider, {"access_token": "access-1", "refresh_token": "refresh-1"})

    response = test_client.delete(f"/connectors/{connector_id}", headers=auth_headers)

    assert response.status_code == 204
    assert revoked == ["refresh-1"], "the refresh token ends the whole grant"
    assert not is_connected(test_client, auth_headers, connector_id)


def test_without_a_refresh_token_the_access_token_is_revoked(test_client, auth_headers, dynamodb_table, google_revoke):
    revoked, _ = google_revoke
    connect("GoogleMail", {"access_token": "access-1"})

    assert test_client.delete("/connectors/google_mail", headers=auth_headers).status_code == 204
    assert revoked == ["access-1"]


def test_a_failed_revoke_still_disconnects(test_client, auth_headers, dynamodb_table, google_revoke):
    _, answer = google_revoke
    answer["status"] = 400  # Google already refuses the token: it expired or the person revoked it themselves
    connect("GoogleMail", {"access_token": "access-1", "refresh_token": "refresh-1"})

    assert test_client.delete("/connectors/google_mail", headers=auth_headers).status_code == 204
    assert not is_connected(test_client, auth_headers, "google_mail")


def test_credentials_that_cannot_be_read_are_still_removed(test_client, auth_headers, dynamodb_table, google_revoke):
    revoked, _ = google_revoke
    ProviderSettingsRepository().save(ProviderSettings(
        account_id=account_for(TEST_USER_EMAIL), provider_name="GoogleMail",
        encrypted_credentials="not-encrypted", auth_type="oauth",
    ))

    assert test_client.delete("/connectors/google_mail", headers=auth_headers).status_code == 204
    assert revoked == [] and not is_connected(test_client, auth_headers, "google_mail")


def test_disconnecting_one_connector_leaves_the_others(test_client, auth_headers, dynamodb_table, google_revoke):
    connect("GoogleMail", {"access_token": "mail"})
    connect("GoogleDrive", {"access_token": "drive"})

    test_client.delete("/connectors/google_mail", headers=auth_headers)

    assert is_connected(test_client, auth_headers, "google_drive")


def test_disconnecting_what_is_not_connected_or_unknown_is_not_found(test_client, auth_headers, dynamodb_table):
    assert test_client.delete("/connectors/google_mail", headers=auth_headers).status_code == 404
    assert test_client.delete("/connectors/no_such_connector", headers=auth_headers).status_code == 404
