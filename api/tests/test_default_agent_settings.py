"""Tests for the default-agent settings router endpoints."""

from fastapi.testclient import TestClient

from src.agents.models import Agent
from tests.mock_data import AGENT_CREATE_REQUEST, AGENT_CREATE_REQUEST_2, TEST_USER_EMAIL, TEST_USER_EMAIL_2


def _create_agent(test_client: TestClient, auth_headers: dict, request: dict | None = None) -> str:
    response = test_client.post("/agents", json=request or AGENT_CREATE_REQUEST, headers=auth_headers)
    assert response.status_code == 201
    return response.json()["agent_id"]


class TestDefaultAgentSettingsRouter:
    def test_get_default_agent_with_nothing_set_returns_none(self, test_client: TestClient, auth_headers: dict):
        response = test_client.get("/settings/default-agent", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == {"agent_id": None, "updated_at": None}

    def test_set_and_get_default_agent(self, test_client: TestClient, auth_headers: dict):
        agent_id = _create_agent(test_client, auth_headers)

        put_response = test_client.put(
            "/settings/default-agent",
            json={"agent_id": agent_id},
            headers=auth_headers,
        )
        assert put_response.status_code == 200
        assert put_response.json()["agent_id"] == agent_id

        get_response = test_client.get("/settings/default-agent", headers=auth_headers)
        assert get_response.status_code == 200
        assert get_response.json()["agent_id"] == agent_id

    def test_set_default_agent_rejects_agent_not_owned_by_user(self, test_client: TestClient, auth_headers: dict):
        response = test_client.put(
            "/settings/default-agent",
            json={"agent_id": "does-not-exist"},
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_updating_default_agent_overwrites_the_previous_choice(
        self, test_client: TestClient, auth_headers: dict, agent_repository
    ):
        # Two agents for the same user, inserted directly to bypass the per-user agent-creation rate limit.
        first_agent_id = agent_repository.save(
            Agent(created_by=TEST_USER_EMAIL, **AGENT_CREATE_REQUEST)
        ).agent_id
        second_agent_id = agent_repository.save(
            Agent(created_by=TEST_USER_EMAIL, **AGENT_CREATE_REQUEST_2)
        ).agent_id

        test_client.put("/settings/default-agent", json={"agent_id": first_agent_id}, headers=auth_headers)
        test_client.put("/settings/default-agent", json={"agent_id": second_agent_id}, headers=auth_headers)

        get_response = test_client.get("/settings/default-agent", headers=auth_headers)
        assert get_response.json()["agent_id"] == second_agent_id

    def test_clear_default_agent(self, test_client: TestClient, auth_headers: dict):
        agent_id = _create_agent(test_client, auth_headers)
        test_client.put("/settings/default-agent", json={"agent_id": agent_id}, headers=auth_headers)

        delete_response = test_client.delete("/settings/default-agent", headers=auth_headers)
        assert delete_response.status_code == 204

        get_response = test_client.get("/settings/default-agent", headers=auth_headers)
        assert get_response.json()["agent_id"] is None

    def test_default_agent_endpoints_require_auth(self, test_client: TestClient):
        assert test_client.get("/settings/default-agent").status_code == 401
        assert test_client.put("/settings/default-agent", json={"agent_id": "x"}).status_code == 401
        assert test_client.delete("/settings/default-agent").status_code == 401

    def test_default_agent_is_scoped_per_user(self, test_client: TestClient, auth_headers: dict):
        import jwt
        from datetime import datetime, timedelta, timezone

        agent_id = _create_agent(test_client, auth_headers)
        test_client.put("/settings/default-agent", json={"agent_id": agent_id}, headers=auth_headers)

        other_user_token = jwt.encode(
            {
                "sub": TEST_USER_EMAIL_2,
                "name": "Other User",
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
                "iat": datetime.now(timezone.utc),
            },
            "test-secret",
            algorithm="HS256",
        )

        response = test_client.get(
            "/settings/default-agent",
            headers={"Authorization": f"Bearer {other_user_token}"},
        )
        assert response.json()["agent_id"] is None
