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
from src.skills.google_ads.models import GoogleAdsCredentials
from src.skills.google_ads.oauth import GoogleAdsOAuthState, encode_state_session
from tests.mock_data import TEST_USER_EMAIL


def _create_agent_for_user(user_email: str) -> Agent:
    return AgentRepository().save(
        Agent(
            agent_name="Google Ads OAuth Agent",
            agent_architecture="krishna-memgpt",
            agent_provider="Bedrock",
            agent_model="claude-3-7-sonnet",
            agent_persona="Helpful",
            created_by=user_email,
        )
    )


def _state(**overrides) -> str:
    values = {
        "nonce": "nonce",
        "user_email": TEST_USER_EMAIL,
        "agent_id": "agent-1",
        "skill_id": "google_ads",
        "return_to": "http://localhost:5173/dashboard/agents/agent-1/skills",
        "expires_at": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
    }
    return encode_state_session(GoogleAdsOAuthState(**{**values, **overrides}))


class TestGoogleAdsOAuth:
    def test_start_requires_auth(self, test_client: TestClient):
        response = test_client.post(
            "/auth/google-ads/start",
            json={"agent_id": "agent-1", "skill_id": "google_ads", "return_to": "http://localhost:5173/x"},
        )
        assert response.status_code == 401

    def test_start_asks_only_for_the_adwords_scope_with_offline_access(self, test_client: TestClient, auth_headers: dict):
        agent = _create_agent_for_user(TEST_USER_EMAIL)
        response = test_client.post(
            "/auth/google-ads/start",
            json={
                "agent_id": agent.agent_id,
                "skill_id": "google_ads",
                "return_to": f"http://localhost:5173/dashboard/agents/{agent.agent_id}/skills",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        query = parse_qs(urlparse(response.json()["authorize_url"]).query)
        assert query["client_id"] == [settings.google_client_id]
        assert query["redirect_uri"] == [settings.google_ads_redirect_uri]
        assert query["scope"] == ["https://www.googleapis.com/auth/adwords"]
        assert query["access_type"] == ["offline"]
        assert query["prompt"] == ["consent"]

    def test_callback_saves_oauth_credentials_only(self, test_client: TestClient, monkeypatch):
        async def mock_build_credentials(code: str):
            assert code == "test-code"
            return GoogleAdsCredentials(
                access_token="ads-access-token",
                refresh_token="ads-refresh-token",
                scope=settings.google_ads_oauth_scopes,
            )

        monkeypatch.setattr("src.auth.router.build_google_ads_credentials_from_auth_code", mock_build_credentials)

        response = test_client.get(
            "/auth/google-ads/callback",
            params={"code": "test-code", "state": _state()},
            follow_redirects=False,
        )

        assert response.status_code in {302, 307}
        params = parse_qs(urlparse(response.headers["location"]).query)
        assert params["skill_oauth"] == ["success"]
        assert params["google_ads_oauth"] == ["success"]
        assert params["skill_id"] == ["google_ads"]

        saved = ProviderSettingsRepository().find_by_provider(TEST_USER_EMAIL, "GoogleAds")
        assert saved is not None and saved.auth_type == "oauth"
        credentials = json.loads(decrypt(saved.encrypted_credentials))
        assert credentials["access_token"] == "ads-access-token"
        assert credentials["refresh_token"] == "ads-refresh-token"
        assert "developer_token" not in credentials

    def test_callback_with_invalid_state_redirects_to_error(self, test_client: TestClient):
        response = test_client.get(
            "/auth/google-ads/callback",
            params={"code": "test-code", "state": "bad-state"},
            follow_redirects=False,
        )
        params = parse_qs(urlparse(response.headers["location"]).query)
        assert params["skill_oauth"] == ["error"]
        assert params["google_ads_oauth"] == ["error"]

    def test_catalog_offers_google_ads_through_its_oauth_connector(self, test_client: TestClient, auth_headers: dict):
        catalog = test_client.get("/skills", headers=auth_headers).json()
        google_ads = next(item for item in catalog if item["skill_id"] == "google_ads")
        assert google_ads["requires_oauth"] is True
        assert google_ads["oauth_provider_name"] == "GoogleAds"
        assert google_ads["oauth_start_path"] == "/auth/google-ads/start"
        assert google_ads["oauth_connected"] is False
