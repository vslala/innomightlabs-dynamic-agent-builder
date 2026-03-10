import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from src.config import settings
from src.crypto import decrypt
from src.auth.openai_oauth import encode_state_session, OpenAIOAuthState
from src.settings.repository import ProviderSettingsRepository
from tests.mock_data import TEST_USER_EMAIL


class TestOpenAIOAuth:
    def test_openai_start_requires_auth(self, test_client: TestClient):
        response = test_client.post("/auth/openai/start", json={})
        assert response.status_code == 401

    def test_openai_start_returns_authorize_url(self, test_client: TestClient, auth_headers: dict):
        response = test_client.post("/auth/openai/start", json={}, headers=auth_headers)

        assert response.status_code == 200
        payload = response.json()
        assert "authorize_url" in payload
        assert payload["authorize_url"].startswith("https://auth.openai.com/oauth/authorize?")

    def test_openai_complete_success_saves_provider_settings(
        self,
        test_client: TestClient,
        auth_headers: dict,
        monkeypatch,
    ):
        async def mock_build_credentials(code: str, code_verifier: str):
            assert code == "test-code"
            assert code_verifier
            from src.auth.openai_oauth import OpenAICredentials
            return OpenAICredentials(
                access_token="header.payload.signature",
                refresh_token="refresh-123",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                scope="openid profile email offline_access",
                token_type="Bearer",
            )

        monkeypatch.setattr("src.auth.router.build_credentials_from_auth_code", mock_build_credentials)

        start_response = test_client.post("/auth/openai/start", json={}, headers=auth_headers)
        assert start_response.status_code == 200
        authorize_url = start_response.json()["authorize_url"]
        state = parse_qs(urlparse(authorize_url).query)["state"][0]
        callback_url = f"{settings.openai_oauth_redirect_uri}?code=test-code&state={state}"

        response = test_client.post(
            "/auth/openai/complete",
            json={"callback_url": callback_url},
            headers=auth_headers,
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["provider_name"] == "OpenAI"
        assert payload["is_configured"] is True

        repo = ProviderSettingsRepository()
        saved = repo.find_by_provider(TEST_USER_EMAIL, "OpenAI")
        assert saved is not None
        assert saved.auth_type == "oauth"

        credentials = json.loads(decrypt(saved.encrypted_credentials))
        assert credentials["access_token"] == "header.payload.signature"
        assert credentials["refresh_token"] == "refresh-123"
        assert "expires_at" in credentials

    def test_openai_complete_rejects_invalid_callback_url(
        self,
        test_client: TestClient,
        auth_headers: dict,
    ):
        response = test_client.post(
            "/auth/openai/complete",
            json={"callback_url": "not-a-url"},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "full callback URL" in response.json()["detail"]

    def test_openai_complete_invalid_state_returns_400(
        self,
        test_client: TestClient,
        auth_headers: dict,
    ):
        callback_url = f"{settings.openai_oauth_redirect_uri}?code=test-code&state=bad-state"
        response = test_client.post(
            "/auth/openai/complete",
            json={"callback_url": callback_url},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Invalid OpenAI OAuth state" in response.json()["detail"]

    def test_callback_page_for_openai_state_returns_manual_instructions(
        self,
        test_client: TestClient,
    ):
        state_session = OpenAIOAuthState(
            nonce="nonce-test",
            code_verifier="test-verifier",
            user_email=TEST_USER_EMAIL,
            return_to="http://localhost:5173/dashboard/settings",
            expires_at=int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
        )
        encrypted_state = encode_state_session(state_session)

        response = test_client.get("/auth/callback", params={"state": encrypted_state})

        assert response.status_code == 200
        assert "Copy the full URL" in response.text


class TestOpenAISettings:
    def test_openai_manual_settings_post_is_rejected(self, test_client: TestClient, auth_headers: dict):
        response = test_client.post(
            "/settings/providers/OpenAI",
            json={"api_key": "should-not-work"},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "OAuth" in response.json()["detail"]
