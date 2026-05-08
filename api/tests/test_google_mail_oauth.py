from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.config import settings
from src.crypto import decrypt
from src.settings.repository import ProviderSettingsRepository
from src.skills.google_mail.models import GoogleMailCredentials
from src.skills.google_mail.oauth import GoogleMailOAuthState, encode_state_session
from tests.mock_data import TEST_USER_EMAIL


def _create_agent_for_user(user_email: str) -> Agent:
    repo = AgentRepository()
    agent = Agent(
        agent_name="Google Mail OAuth Agent",
        agent_architecture="krishna-memgpt",
        agent_provider="Bedrock",
        agent_model="claude-3-7-sonnet",
        agent_persona="Helpful",
        created_by=user_email,
    )
    return repo.save(agent)


class TestGoogleMailOAuth:
    def test_google_mail_start_requires_auth(self, test_client: TestClient):
        response = test_client.post(
            "/auth/google-mail/start",
            json={
                "agent_id": "agent-1",
                "skill_id": "google_mail",
                "return_to": "http://localhost:5173/dashboard/agents/agent-1/skills",
            },
        )

        assert response.status_code == 401

    def test_google_mail_start_returns_authorize_url(self, test_client: TestClient, auth_headers: dict):
        agent = _create_agent_for_user(TEST_USER_EMAIL)
        response = test_client.post(
            "/auth/google-mail/start",
            json={
                "agent_id": agent.agent_id,
                "skill_id": "google_mail",
                "return_to": f"http://localhost:5173/dashboard/agents/{agent.agent_id}/skills",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["authorize_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")

        query = parse_qs(urlparse(payload["authorize_url"]).query)
        assert query["client_id"] == [settings.google_client_id]
        assert query["redirect_uri"] == [settings.google_mail_redirect_uri]
        assert query["scope"] == [settings.google_mail_oauth_scopes]
        assert "state" in query

    def test_google_mail_callback_saves_provider_settings(
        self,
        test_client: TestClient,
        monkeypatch,
    ):
        async def mock_build_credentials(code: str):
            assert code == "test-code"
            return GoogleMailCredentials(
                access_token="mail-access-token",
                refresh_token="mail-refresh-token",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                scope=settings.google_mail_oauth_scopes,
                token_type="Bearer",
            )

        monkeypatch.setattr("src.auth.router.build_google_mail_credentials_from_auth_code", mock_build_credentials)

        state = encode_state_session(
            GoogleMailOAuthState(
                nonce="nonce",
                user_email=TEST_USER_EMAIL,
                agent_id="agent-1",
                skill_id="google_mail",
                return_to="http://localhost:5173/dashboard/agents/agent-1/skills",
                expires_at=int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
            )
        )

        response = test_client.get(
            "/auth/google-mail/callback",
            params={"code": "test-code", "state": state},
            follow_redirects=False,
        )

        assert response.status_code in {302, 307}
        location = response.headers["location"]
        params = parse_qs(urlparse(location).query)
        assert params["skill_oauth"] == ["success"]
        assert params["google_mail_oauth"] == ["success"]
        assert params["agent_id"] == ["agent-1"]
        assert params["skill_id"] == ["google_mail"]

        repo = ProviderSettingsRepository()
        saved = repo.find_by_provider(TEST_USER_EMAIL, "GoogleMail")
        assert saved is not None
        assert saved.auth_type == "oauth"

        credentials = json.loads(decrypt(saved.encrypted_credentials))
        assert credentials["access_token"] == "mail-access-token"
        assert credentials["refresh_token"] == "mail-refresh-token"

    def test_google_mail_callback_invalid_state_redirects_to_error(self, test_client: TestClient):
        response = test_client.get(
            "/auth/google-mail/callback",
            params={"code": "test-code", "state": "bad-state"},
            follow_redirects=False,
        )

        assert response.status_code in {302, 307}
        location = response.headers["location"]
        params = parse_qs(urlparse(location).query)
        assert params["skill_oauth"] == ["error"]
        assert params["google_mail_oauth"] == ["error"]
