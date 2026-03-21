import asyncio
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.auth.google_drive_oauth import (
    GoogleDriveCredentials,
    encode_state_session,
    GoogleDriveOAuthState,
    force_refresh_google_drive_credentials,
)
from src.config import settings
from src.crypto import decrypt, encrypt
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from tests.mock_data import TEST_USER_EMAIL


def _create_agent_for_user(user_email: str) -> Agent:
    repo = AgentRepository()
    agent = Agent(
        agent_name="Google Drive OAuth Agent",
        agent_architecture="krishna-memgpt",
        agent_provider="Bedrock",
        agent_model="claude-3-7-sonnet",
        agent_persona="Helpful",
        created_by=user_email,
    )
    return repo.save(agent)


class TestGoogleDriveOAuth:
    def test_google_drive_start_requires_auth(self, test_client: TestClient):
        response = test_client.post(
            "/auth/google-drive/start",
            json={"agent_id": "agent-1", "skill_id": "google_drive", "return_to": "http://localhost:5173/dashboard/agents/agent-1"},
        )
        assert response.status_code == 401

    def test_google_drive_start_returns_authorize_url(self, test_client: TestClient, auth_headers: dict):
        agent = _create_agent_for_user(TEST_USER_EMAIL)
        response = test_client.post(
            "/auth/google-drive/start",
            json={
                "agent_id": agent.agent_id,
                "skill_id": "google_drive",
                "return_to": f"http://localhost:5173/dashboard/agents/{agent.agent_id}",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["authorize_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")

        query = parse_qs(urlparse(payload["authorize_url"]).query)
        assert query["client_id"] == [settings.google_client_id]
        assert query["redirect_uri"] == [settings.google_drive_redirect_uri]
        assert query["scope"] == [settings.google_drive_oauth_scopes]
        assert "state" in query

    def test_google_drive_callback_saves_provider_settings(
        self,
        test_client: TestClient,
        monkeypatch,
    ):
        async def mock_build_credentials(code: str):
            assert code == "test-code"
            return GoogleDriveCredentials(
                access_token="drive-access-token",
                refresh_token="drive-refresh-token",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                scope=settings.google_drive_oauth_scopes,
                token_type="Bearer",
            )

        monkeypatch.setattr("src.auth.router.build_google_drive_credentials_from_auth_code", mock_build_credentials)

        state = encode_state_session(
            GoogleDriveOAuthState(
                nonce="nonce",
                user_email=TEST_USER_EMAIL,
                agent_id="agent-1",
                skill_id="google_drive",
                return_to="http://localhost:5173/dashboard/agents/agent-1",
                expires_at=int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
            )
        )

        response = test_client.get(
            "/auth/google-drive/callback",
            params={"code": "test-code", "state": state},
            follow_redirects=False,
        )

        assert response.status_code in {302, 307}
        location = response.headers["location"]
        params = parse_qs(urlparse(location).query)
        assert params["google_drive_oauth"] == ["success"]
        assert params["agent_id"] == ["agent-1"]
        assert params["skill_id"] == ["google_drive"]

        repo = ProviderSettingsRepository()
        saved = repo.find_by_provider(TEST_USER_EMAIL, "GoogleDrive")
        assert saved is not None
        assert saved.auth_type == "oauth"

        credentials = json.loads(decrypt(saved.encrypted_credentials))
        assert credentials["access_token"] == "drive-access-token"
        assert credentials["refresh_token"] == "drive-refresh-token"

    def test_google_drive_callback_invalid_state_redirects_to_error(self, test_client: TestClient):
        response = test_client.get(
            "/auth/google-drive/callback",
            params={"code": "test-code", "state": "bad-state"},
            follow_redirects=False,
        )

        assert response.status_code in {302, 307}
        location = response.headers["location"]
        params = parse_qs(urlparse(location).query)
        assert params["google_drive_oauth"] == ["error"]

    def test_force_refresh_google_drive_credentials_updates_storage(self, dynamodb_table, monkeypatch):
        repo = ProviderSettingsRepository()
        provider_settings = ProviderSettings(
            user_email=TEST_USER_EMAIL,
            provider_name="GoogleDrive",
            encrypted_credentials=encrypt(
                GoogleDriveCredentials(
                    access_token="old-access",
                    refresh_token="old-refresh",
                    expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
                    scope=settings.google_drive_oauth_scopes,
                    token_type="Bearer",
                ).model_dump_json()
            ),
            auth_type="oauth",
        )
        repo.save(provider_settings)

        async def mock_refresh(refresh_token: str):
            assert refresh_token == "old-refresh"
            return {
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 3600,
                "scope": settings.google_drive_oauth_scopes,
                "token_type": "Bearer",
            }

        monkeypatch.setattr("src.auth.google_drive_oauth.refresh_access_token", mock_refresh)

        refreshed = force_refresh_google_drive_credentials(provider_settings, repo)
        credentials = asyncio.run(refreshed)
        assert credentials.access_token == "new-access"
        assert credentials.refresh_token == "new-refresh"

        saved = repo.find_by_provider(TEST_USER_EMAIL, "GoogleDrive")
        assert saved is not None
        payload = json.loads(decrypt(saved.encrypted_credentials))
        assert payload["access_token"] == "new-access"
