"""A connect flow stores credentials only for the signed-in user who started it."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from src.settings.repository import ProviderSettingsRepository
from src.skills.google_mail.models import GoogleMailCredentials
from src.skills.google_mail.oauth import GoogleMailOAuthState, encode_state_session
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2
from tests.oauth_handoff import handoff_result, owner_headers

ATTACKER = TEST_USER_EMAIL_2


def _attackers_state() -> str:
    return encode_state_session(
        GoogleMailOAuthState(
            nonce="nonce",
            user_email=ATTACKER,
            agent_id="attacker-agent",
            skill_id="google_mail",
            return_to="http://localhost:5173/dashboard/agents/attacker-agent/skills",
            expires_at=int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
        )
    )


def test_a_victim_completing_an_attackers_consent_link_stores_nothing(test_client: TestClient, monkeypatch):
    async def victims_google_account(code: str):
        return GoogleMailCredentials(
            access_token="victim-access", refresh_token="victim-refresh",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1), scope="mail", token_type="Bearer",
        )

    monkeypatch.setattr("src.auth.router.build_google_mail_credentials_from_auth_code", victims_google_account)
    callback = test_client.get(
        "/auth/google-mail/callback", params={"code": "victims-code", "state": _attackers_state()}, follow_redirects=False
    )

    assert handoff_result(test_client, callback, TEST_USER_EMAIL)["reason"] == ["invalid_state"]
    assert ProviderSettingsRepository().find_by_provider(ATTACKER, "GoogleMail") is None
    assert ProviderSettingsRepository().find_by_provider(TEST_USER_EMAIL, "GoogleMail") is None


def test_the_callback_itself_stores_nothing(test_client: TestClient, monkeypatch):
    async def must_not_run(code: str):
        raise AssertionError("credentials are only exchanged once the SPA completes the flow")

    monkeypatch.setattr("src.auth.router.build_google_mail_credentials_from_auth_code", must_not_run)

    response = test_client.get(
        "/auth/google-mail/callback", params={"code": "c", "state": _attackers_state()}, follow_redirects=False
    )

    assert response.status_code == 307
    assert response.headers["location"].startswith("http://localhost:5173/dashboard/agents/attacker-agent/skills?")


def test_a_tampered_completion_is_refused(test_client: TestClient):
    response = test_client.post("/connectors/oauth/complete", json={"completion": "garbage"}, headers=owner_headers())

    assert response.status_code == 400


def test_connect_flows_only_return_to_this_app(test_client: TestClient, monkeypatch):
    monkeypatch.setattr("src.config.settings.is_google_mail_oauth_configured", lambda: True)
    response = test_client.post(
        "/connectors/google_mail/start",
        json={"return_to": "https://attacker.example/landing"},
        headers=owner_headers(),
    )

    assert response.status_code == 400


def _a2a_install(agent_id: str) -> str:
    from src.skills.repository import AgentSkillRepository

    AgentSkillRepository().upsert_with_config(
        agent_id=agent_id, installed_skill_id="agent2agent_client:test", skill_id="agent2agent_client",
        namespace="core.agent2agent", skill_name="Agent2Agent Client", skill_description="", enabled=True,
        installed_by=TEST_USER_EMAIL, plain_config={"registry_set_name": "Test", "registry_urls": "https://registry.test/a2a/agents"},
        secret_config={}, secret_fields=[],
    )
    return "agent2agent_client:test"


def _fake_remote_agent(monkeypatch) -> None:
    from src.skills.agent2agent_client.models import RegistryAgentCandidate
    from src.skills.agent2agent_client.oauth import A2ARemoteOAuthProviderConfig

    class FakeDiscovery:
        class http_client:
            @staticmethod
            async def get_agent_card(url):
                return {"name": "Calendar"}

        async def _load_candidates(self, config):
            return [RegistryAgentCandidate(
                registry_url="https://registry.test/a2a/agents", service_url="https://registry.test/a2a/agents/calendar",
                card_url="https://registry.test/a2a/agents/calendar/card", name="Calendar",
            )]

    async def provider(**kwargs):
        return A2ARemoteOAuthProviderConfig(
            authorization_url="https://registry.test/oauth/authorize", token_url="https://registry.test/oauth/token",
            client_id="calendar-client", client_secret="s", scope="calendar.read", target_origin="https://registry.test",
        )

    monkeypatch.setattr("src.skills.agent2agent_client.router.A2ADiscoveryClient", FakeDiscovery)
    monkeypatch.setattr("src.skills.agent2agent_client.router.authorization_code_provider_from_card_with_dcr", provider)


def test_a2a_connect_starts_and_only_returns_to_this_app(test_client: TestClient, auth_headers, monkeypatch):
    from tests.mock_data import AGENT_CREATE_REQUEST

    agent_id = test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=auth_headers).json()["agent_id"]
    installed_skill_id = _a2a_install(agent_id)
    _fake_remote_agent(monkeypatch)
    body = {"agent_id": agent_id, "installed_skill_id": installed_skill_id}

    started = test_client.post(
        "/skills/agent2agent_client/oauth/start",
        json={**body, "return_to": f"http://localhost:5173/dashboard/agents/{agent_id}/skills"},
        headers=auth_headers,
    )
    off_site = test_client.post(
        "/skills/agent2agent_client/oauth/start", json={**body, "return_to": "https://attacker.example/"}, headers=auth_headers
    )

    assert started.status_code == 200, started.text
    assert started.json()["authorize_url"].startswith("https://registry.test/oauth/authorize?")
    assert off_site.status_code == 400
