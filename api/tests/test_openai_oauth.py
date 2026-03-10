import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from src.crypto import decrypt
from src.auth.openai_oauth import encode_state_session, OpenAIOAuthState
from src.settings.repository import ProviderSettingsRepository
from tests.mock_data import TEST_USER_EMAIL


class TestOpenAIOAuth:
    def test_openai_start_requires_auth(self, test_client: TestClient):
        response = test_client.post("/auth/openai/start", json={})
        assert response.status_code == 401

    def test_openai_start_returns_authorize_url(self, test_client: TestClient, auth_headers: dict):
        response = test_client.post(
            "/auth/openai/start",
            json={"return_to": "http://localhost:5173/dashboard/settings"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        payload = response.json()
        assert "authorize_url" in payload
        assert payload["authorize_url"].startswith("https://auth.openai.com/oauth/authorize?")

    def test_openai_callback_success_saves_provider_settings(
        self,
        test_client: TestClient,
        monkeypatch,
    ):
        async def mock_build_credentials(code: str, code_verifier: str):
            assert code == "test-code"
            assert code_verifier == "test-verifier"
            from src.auth.openai_oauth import OpenAICredentials
            return OpenAICredentials(
                access_token="header.payload.signature",
                refresh_token="refresh-123",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                scope="openid profile email offline_access",
                token_type="Bearer",
            )

        monkeypatch.setattr("src.auth.router.build_credentials_from_auth_code", mock_build_credentials)

        state_session = OpenAIOAuthState(
            nonce="nonce-test",
            code_verifier="test-verifier",
            user_email=TEST_USER_EMAIL,
            return_to="http://localhost:5173/dashboard/settings",
            expires_at=int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
        )

        response = test_client.get(
            "/auth/openai",
            params={"code": "test-code", "state": encode_state_session(state_session)},
            follow_redirects=False,
        )

        assert response.status_code in (302, 307)
        assert "openai_oauth=success" in response.headers["location"]

        repo = ProviderSettingsRepository()
        saved = repo.find_by_provider(TEST_USER_EMAIL, "OpenAI")
        assert saved is not None
        assert saved.auth_type == "oauth"

        credentials = json.loads(decrypt(saved.encrypted_credentials))
        assert credentials["access_token"] == "header.payload.signature"
        assert credentials["refresh_token"] == "refresh-123"
        assert "expires_at" in credentials

    def test_openai_callback_invalid_state_redirects_error(
        self,
        test_client: TestClient,
    ):
        response = test_client.get(
            "/auth/openai",
            params={"code": "test-code", "state": "different-state"},
            follow_redirects=False,
        )

        assert response.status_code in (302, 307)
        assert "openai_oauth=error" in response.headers["location"]

    def test_openai_callback_works_without_cookie_when_state_contains_session(
        self,
        test_client: TestClient,
        monkeypatch,
    ):
        async def mock_build_credentials(code: str, code_verifier: str):
            assert code == "test-code"
            assert code_verifier == "test-verifier"
            from src.auth.openai_oauth import OpenAICredentials
            return OpenAICredentials(
                access_token="header.payload.signature",
                refresh_token="refresh-123",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )

        monkeypatch.setattr("src.auth.router.build_credentials_from_auth_code", mock_build_credentials)

        state_session = OpenAIOAuthState(
            nonce="nonce-test",
            code_verifier="test-verifier",
            user_email=TEST_USER_EMAIL,
            return_to="http://localhost:5173/dashboard/settings",
            expires_at=int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
        )
        encrypted_state = encode_state_session(state_session)

        response = test_client.get(
            "/auth/callback",
            params={"code": "test-code", "state": encrypted_state},
            follow_redirects=False,
        )

        assert response.status_code in (302, 307)
        assert "openai_oauth=success" in response.headers["location"]


class TestOpenAISettings:
    def test_openai_manual_settings_post_is_rejected(self, test_client: TestClient, auth_headers: dict):
        response = test_client.post(
            "/settings/providers/OpenAI",
            json={"api_key": "should-not-work"},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "OAuth" in response.json()["detail"]
