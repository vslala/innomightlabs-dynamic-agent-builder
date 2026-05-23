from urllib.parse import parse_qs, urlparse

from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from tests.mock_data import TEST_USER_EMAIL


def test_list_connectors_reports_status(test_client, auth_headers, dynamodb_table):
    response = test_client.get("/connectors", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    gmail = next(item for item in payload if item["connector_id"] == "google_mail")
    assert gmail["connected"] is False
    assert gmail["connect_path"] == "/connectors/google_mail/start"

    ProviderSettingsRepository().save(
        ProviderSettings(
            user_email=TEST_USER_EMAIL,
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
