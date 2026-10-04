"""
Tests for agent secret keys (public /v1 API credentials).
"""

from datetime import datetime, timedelta, timezone
from typing import cast

import jwt
import pytest
from fastapi.testclient import TestClient

from tests.mock_data import AGENT_CREATE_REQUEST, TEST_USER_EMAIL


class TestAgentSecretKeyModel:
    def test_issue_returns_secret_and_stores_only_its_hash(self):
        from src.public_api.keys import AgentSecretKey, hash_secret

        key, secret = AgentSecretKey.issue(agent_id="agent-123", name="Server", created_by=TEST_USER_EMAIL)

        assert secret.startswith("sk_live_")
        assert key.key_hash == hash_secret(secret)
        assert key.key_hint == f"sk_live_…{secret[-4:]}"
        assert secret not in key.to_dynamo_item().values()

    def test_issue_generates_unique_secrets(self):
        from src.public_api.keys import AgentSecretKey

        secrets = {AgentSecretKey.issue(agent_id="a", name="k", created_by=TEST_USER_EMAIL)[1] for _ in range(20)}

        assert len(secrets) == 20

    def test_response_hides_hash_and_owner(self):
        from src.public_api.keys import AgentSecretKey

        key, _ = AgentSecretKey.issue(agent_id="agent-123", name="Server", created_by=TEST_USER_EMAIL)
        response = key.to_response().model_dump()

        assert "key_hash" not in response
        assert "created_by" not in response
        assert response["key_hint"] == key.key_hint


class TestSecretKeyRepository:
    def _issue(self, repo, agent_id: str = "agent-123"):
        from src.public_api.keys import AgentSecretKey

        key, secret = AgentSecretKey.issue(agent_id=agent_id, name="Server", created_by=TEST_USER_EMAIL)
        repo.create(key)
        return key, secret

    def test_find_by_hash_round_trips(self, dynamodb_table):
        from src.public_api.keys import SecretKeyRepository, hash_secret

        repo = SecretKeyRepository()
        key, secret = self._issue(repo)

        found = repo.find_by_hash(hash_secret(secret))

        assert found is not None
        assert found.key_id == key.key_id
        assert repo.find_by_hash(hash_secret("sk_live_wrong")) is None

    def test_find_all_by_agent_only_returns_that_agents_keys(self, dynamodb_table):
        from src.public_api.keys import SecretKeyRepository

        repo = SecretKeyRepository()
        self._issue(repo, "agent-123")
        self._issue(repo, "agent-123")
        self._issue(repo, "agent-456")

        assert len(repo.find_all_by_agent("agent-123")) == 2

    def test_update_changes_only_given_fields_and_keeps_counters(self, dynamodb_table):
        from src.public_api.keys import SecretKeyRepository

        repo = SecretKeyRepository()
        key, _ = self._issue(repo)
        repo.record_request(key.agent_id, key.key_id)

        updated = repo.update(key.agent_id, key.key_id, is_active=False)

        assert updated is not None
        assert updated.is_active is False
        assert updated.name == "Server"
        assert updated.request_count == 1

    def test_update_unknown_key_returns_none(self, dynamodb_table):
        from src.public_api.keys import SecretKeyRepository

        assert SecretKeyRepository().update("agent-123", "missing", name="New") is None

    def test_record_request_counts_and_sets_last_used(self, dynamodb_table):
        from src.public_api.keys import SecretKeyRepository

        repo = SecretKeyRepository()
        key, _ = self._issue(repo)

        repo.record_request(key.agent_id, key.key_id)
        repo.record_request(key.agent_id, key.key_id)

        found = repo.find_by_id(key.agent_id, key.key_id)
        assert found is not None
        assert found.request_count == 2
        assert found.last_used_at is not None

    def test_record_request_does_not_create_unknown_keys(self, dynamodb_table):
        from botocore.exceptions import ClientError

        from src.public_api.keys import SecretKeyRepository

        repo = SecretKeyRepository()

        with pytest.raises(ClientError):
            repo.record_request("agent-123", "missing")
        assert repo.find_by_id("agent-123", "missing") is None

    def test_delete_by_id(self, dynamodb_table):
        from src.public_api.keys import SecretKeyRepository

        repo = SecretKeyRepository()
        key, _ = self._issue(repo)

        repo.delete_by_id(key.agent_id, key.key_id)

        assert repo.find_by_id(key.agent_id, key.key_id) is None


class TestSecretKeysRouter:
    def _create_agent(self, test_client: TestClient, auth_headers: dict) -> str:
        response = test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=auth_headers)
        return cast(str, response.json()["agent_id"])

    def _create_key(self, test_client: TestClient, auth_headers: dict, agent_id: str, name: str = "Server") -> dict:
        response = test_client.post(f"/agents/{agent_id}/secret-keys", json={"name": name}, headers=auth_headers)
        assert response.status_code == 201
        return cast(dict, response.json())

    def _other_user_headers(self) -> dict:
        token = jwt.encode(
            {
                "aud": "owner",
                "sub": "someone-else@example.com",
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
                "iat": datetime.now(timezone.utc),
            },
            "test-secret",
            algorithm="HS256",
        )
        return {"Authorization": f"Bearer {token}"}

    def test_create_returns_secret_once(self, test_client: TestClient, auth_headers: dict):
        agent_id = self._create_agent(test_client, auth_headers)

        created = self._create_key(test_client, auth_headers, agent_id)

        assert created["secret"].startswith("sk_live_")
        assert created["key_hint"].endswith(created["secret"][-4:])
        assert created["agent_id"] == agent_id
        assert created["is_active"] is True

        listed = test_client.get(f"/agents/{agent_id}/secret-keys", headers=auth_headers).json()
        fetched = test_client.get(f"/agents/{agent_id}/secret-keys/{created['key_id']}", headers=auth_headers).json()
        for body in (listed[0], fetched):
            assert "secret" not in body
            assert "key_hash" not in body

    def test_list_returns_newest_first(self, test_client: TestClient, auth_headers: dict):
        agent_id = self._create_agent(test_client, auth_headers)
        self._create_key(test_client, auth_headers, agent_id, "First")
        self._create_key(test_client, auth_headers, agent_id, "Second")

        listed = test_client.get(f"/agents/{agent_id}/secret-keys", headers=auth_headers).json()

        assert [key["name"] for key in listed] == ["Second", "First"]

    def test_update_name_and_status(self, test_client: TestClient, auth_headers: dict):
        agent_id = self._create_agent(test_client, auth_headers)
        created = self._create_key(test_client, auth_headers, agent_id)

        response = test_client.patch(
            f"/agents/{agent_id}/secret-keys/{created['key_id']}",
            json={"name": "Renamed", "is_active": False},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Renamed"
        assert response.json()["is_active"] is False

    def test_update_unknown_key_is_404(self, test_client: TestClient, auth_headers: dict):
        agent_id = self._create_agent(test_client, auth_headers)

        response = test_client.patch(
            f"/agents/{agent_id}/secret-keys/missing", json={"name": "Renamed"}, headers=auth_headers
        )

        assert response.status_code == 404

    def test_delete_is_idempotent(self, test_client: TestClient, auth_headers: dict):
        agent_id = self._create_agent(test_client, auth_headers)
        created = self._create_key(test_client, auth_headers, agent_id)
        url = f"/agents/{agent_id}/secret-keys/{created['key_id']}"

        assert test_client.delete(url, headers=auth_headers).status_code == 204
        assert test_client.delete(url, headers=auth_headers).status_code == 204
        assert test_client.get(url, headers=auth_headers).status_code == 404

    def test_requires_auth(self, test_client: TestClient, auth_headers: dict):
        agent_id = self._create_agent(test_client, auth_headers)

        response = test_client.post(f"/agents/{agent_id}/secret-keys", json={"name": "Server"})

        assert response.status_code == 401

    def test_other_users_cannot_manage_keys(self, test_client: TestClient, auth_headers: dict):
        agent_id = self._create_agent(test_client, auth_headers)
        created = self._create_key(test_client, auth_headers, agent_id)
        other = self._other_user_headers()

        assert test_client.get(f"/agents/{agent_id}/secret-keys", headers=other).status_code == 404
        assert test_client.post(f"/agents/{agent_id}/secret-keys", json={"name": "x"}, headers=other).status_code == 404
        assert (
            test_client.delete(f"/agents/{agent_id}/secret-keys/{created['key_id']}", headers=other).status_code
            == 404
        )
        assert len(test_client.get(f"/agents/{agent_id}/secret-keys", headers=auth_headers).json()) == 1

    def test_unknown_agent_is_404(self, test_client: TestClient, auth_headers: dict):
        response = test_client.post("/agents/no-such-agent/secret-keys", json={"name": "Server"}, headers=auth_headers)

        assert response.status_code == 404
