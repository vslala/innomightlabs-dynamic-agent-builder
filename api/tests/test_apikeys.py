"""
Tests for API Keys module.
"""

import pytest
from fastapi.testclient import TestClient

from tests.mock_data import (
    TEST_USER_EMAIL,
    AGENT_CREATE_REQUEST,
    API_KEY_CREATE_REQUEST,
    API_KEY_CREATE_REQUEST_2,
)


class TestApiKeyModel:
    """Tests for AgentApiKey model."""

    def test_generate_public_key(self):
        """Test public key generation."""
        from src.apikeys.models import generate_public_key

        key = generate_public_key()
        assert key.startswith("pk_live_")
        assert len(key) == 8 + 32  # "pk_live_" + 32 hex chars

    def test_generate_public_key_unique(self):
        """Test that generated keys are unique."""
        from src.apikeys.models import generate_public_key

        keys = {generate_public_key() for _ in range(100)}
        assert len(keys) == 100  # All unique

    def test_api_key_model_defaults(self, dynamodb_table):
        """Test AgentApiKey model default values."""
        from src.apikeys.models import AgentApiKey

        api_key = AgentApiKey(
            agent_id="test-agent",
            name="Test Key",
            created_by=TEST_USER_EMAIL,
        )

        assert api_key.key_id  # UUID generated
        assert api_key.public_key.startswith("pk_live_")
        assert api_key.allowed_origins == []
        assert api_key.is_active is True
        assert api_key.request_count == 0
        assert api_key.last_used_at is None

    def test_api_key_pk_sk_format(self, dynamodb_table):
        """Test partition key and sort key format."""
        from src.apikeys.models import AgentApiKey

        api_key = AgentApiKey(
            agent_id="agent-123",
            name="Test Key",
            created_by=TEST_USER_EMAIL,
        )

        assert api_key.pk == "Agent#agent-123"
        assert api_key.sk.startswith("ApiKey#")

    def test_api_key_gsi2_keys(self, dynamodb_table):
        """Test GSI2 key format for public key lookup."""
        from src.apikeys.models import AgentApiKey

        api_key = AgentApiKey(
            agent_id="agent-123",
            name="Test Key",
            created_by=TEST_USER_EMAIL,
        )

        assert api_key.gsi2_pk == f"ApiKey#{api_key.public_key}"
        assert api_key.gsi2_sk == "Agent#agent-123"

    def test_is_origin_allowed_empty_list(self, dynamodb_table):
        """Test origin validation with empty allowed_origins (allow all)."""
        from src.apikeys.models import AgentApiKey

        api_key = AgentApiKey(
            agent_id="agent-123",
            name="Test Key",
            allowed_origins=[],
            created_by=TEST_USER_EMAIL,
        )

        assert api_key.is_origin_allowed("https://example.com") is True
        assert api_key.is_origin_allowed("https://anything.com") is True
        assert api_key.is_origin_allowed(None) is True

    def test_is_origin_allowed_with_list(self, dynamodb_table):
        """Test origin validation with specified allowed_origins."""
        from src.apikeys.models import AgentApiKey

        api_key = AgentApiKey(
            agent_id="agent-123",
            name="Test Key",
            allowed_origins=["https://example.com", "https://app.example.com"],
            created_by=TEST_USER_EMAIL,
        )

        assert api_key.is_origin_allowed("https://example.com") is True
        assert api_key.is_origin_allowed("https://app.example.com") is True
        assert api_key.is_origin_allowed("https://other.com") is False
        assert api_key.is_origin_allowed(None) is False


class TestApiKeyRepository:
    """Tests for ApiKeyRepository."""

    def test_save_creates_new_api_key(self, dynamodb_table):
        """Test saving a new API key."""
        from src.apikeys.models import AgentApiKey
        from src.apikeys.repository import ApiKeyRepository

        repo = ApiKeyRepository()
        api_key = AgentApiKey(
            agent_id="agent-123",
            name="Test Key",
            created_by=TEST_USER_EMAIL,
        )

        saved = repo.save(api_key)

        assert saved.key_id == api_key.key_id
        assert saved.public_key == api_key.public_key

    def test_find_by_id(self, dynamodb_table):
        """Test finding API key by ID."""
        from src.apikeys.models import AgentApiKey
        from src.apikeys.repository import ApiKeyRepository

        repo = ApiKeyRepository()
        api_key = AgentApiKey(
            agent_id="agent-123",
            name="Test Key",
            created_by=TEST_USER_EMAIL,
        )
        repo.save(api_key)

        found = repo.find_by_id("agent-123", api_key.key_id)

        assert found is not None
        assert found.key_id == api_key.key_id
        assert found.name == "Test Key"

    def test_find_by_id_not_found(self, dynamodb_table):
        """Test finding non-existent API key returns None."""
        from src.apikeys.repository import ApiKeyRepository

        repo = ApiKeyRepository()
        found = repo.find_by_id("agent-123", "non-existent-key")

        assert found is None

    def test_find_by_public_key(self, dynamodb_table):
        """Test finding API key by public key (GSI2)."""
        from src.apikeys.models import AgentApiKey
        from src.apikeys.repository import ApiKeyRepository

        repo = ApiKeyRepository()
        api_key = AgentApiKey(
            agent_id="agent-123",
            name="Test Key",
            created_by=TEST_USER_EMAIL,
        )
        repo.save(api_key)

        found = repo.find_by_public_key(api_key.public_key)

        assert found is not None
        assert found.key_id == api_key.key_id
        assert found.agent_id == "agent-123"

    def test_find_by_public_key_not_found(self, dynamodb_table):
        """Test finding non-existent public key returns None."""
        from src.apikeys.repository import ApiKeyRepository

        repo = ApiKeyRepository()
        found = repo.find_by_public_key("pk_live_nonexistent")

        assert found is None

    def test_find_all_by_agent(self, dynamodb_table):
        """Test finding all API keys for an agent."""
        from src.apikeys.models import AgentApiKey
        from src.apikeys.repository import ApiKeyRepository

        repo = ApiKeyRepository()

        # Create multiple keys for same agent
        for i in range(3):
            api_key = AgentApiKey(
                agent_id="agent-123",
                name=f"Key {i}",
                created_by=TEST_USER_EMAIL,
            )
            repo.save(api_key)

        # Create key for different agent
        other_key = AgentApiKey(
            agent_id="agent-456",
            name="Other Key",
            created_by=TEST_USER_EMAIL,
        )
        repo.save(other_key)

        keys = repo.find_all_by_agent("agent-123")

        assert len(keys) == 3
        assert all(k.agent_id == "agent-123" for k in keys)

    def test_delete_by_id(self, dynamodb_table):
        """Test deleting an API key."""
        from src.apikeys.models import AgentApiKey
        from src.apikeys.repository import ApiKeyRepository

        repo = ApiKeyRepository()
        api_key = AgentApiKey(
            agent_id="agent-123",
            name="Test Key",
            created_by=TEST_USER_EMAIL,
        )
        repo.save(api_key)

        result = repo.delete_by_id("agent-123", api_key.key_id)

        assert result is True
        assert repo.find_by_id("agent-123", api_key.key_id) is None

    def test_delete_all_by_agent(self, dynamodb_table):
        """Test deleting all API keys for an agent."""
        from src.apikeys.models import AgentApiKey
        from src.apikeys.repository import ApiKeyRepository

        repo = ApiKeyRepository()

        # Create multiple keys
        for i in range(3):
            api_key = AgentApiKey(
                agent_id="agent-123",
                name=f"Key {i}",
                created_by=TEST_USER_EMAIL,
            )
            repo.save(api_key)

        deleted = repo.delete_all_by_agent("agent-123")

        assert deleted == 3
        assert len(repo.find_all_by_agent("agent-123")) == 0


class TestApiKeysRouter:
    """Tests for API Keys router endpoints."""

    def _create_agent(self, test_client: TestClient, auth_headers: dict) -> str:
        """Helper to create an agent and return its ID."""
        response = test_client.post(
            "/agents",
            json=AGENT_CREATE_REQUEST,
            headers=auth_headers,
        )
        return response.json()["agent_id"]

    def test_create_api_key_success(self, test_client: TestClient, auth_headers: dict):
        """Test creating a new API key."""
        agent_id = self._create_agent(test_client, auth_headers)

        response = test_client.post(
            f"/agents/{agent_id}/api-keys",
            json=API_KEY_CREATE_REQUEST,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == API_KEY_CREATE_REQUEST["name"]
        assert data["allowed_origins"] == API_KEY_CREATE_REQUEST["allowed_origins"]
        assert data["agent_id"] == agent_id
        assert data["public_key"].startswith("pk_live_")
        assert data["is_active"] is True
        assert data["created_by"] == TEST_USER_EMAIL

    def test_create_api_key_for_invalid_agent(self, test_client: TestClient, auth_headers: dict):
        """Test creating API key for non-existent agent returns 404."""
        response = test_client.post(
            "/agents/non-existent-agent/api-keys",
            json=API_KEY_CREATE_REQUEST,
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_create_api_key_requires_auth(self, test_client: TestClient, auth_headers: dict):
        """Test that creating API key requires authentication."""
        agent_id = self._create_agent(test_client, auth_headers)

        response = test_client.post(
            f"/agents/{agent_id}/api-keys",
            json=API_KEY_CREATE_REQUEST,
        )

        assert response.status_code == 401

    def test_list_api_keys(self, test_client: TestClient, auth_headers: dict):
        """Test listing all API keys for an agent."""
        agent_id = self._create_agent(test_client, auth_headers)

        # Create two keys
        test_client.post(
            f"/agents/{agent_id}/api-keys",
            json=API_KEY_CREATE_REQUEST,
            headers=auth_headers,
        )
        test_client.post(
            f"/agents/{agent_id}/api-keys",
            json=API_KEY_CREATE_REQUEST_2,
            headers=auth_headers,
        )

        response = test_client.get(
            f"/agents/{agent_id}/api-keys",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = {k["name"] for k in data}
        assert "Production Key" in names
        assert "Development Key" in names

    def test_get_api_key_by_id(self, test_client: TestClient, auth_headers: dict):
        """Test getting a single API key by ID."""
        agent_id = self._create_agent(test_client, auth_headers)

        create_response = test_client.post(
            f"/agents/{agent_id}/api-keys",
            json=API_KEY_CREATE_REQUEST,
            headers=auth_headers,
        )
        key_id = create_response.json()["key_id"]

        response = test_client.get(
            f"/agents/{agent_id}/api-keys/{key_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["key_id"] == key_id
        assert data["name"] == API_KEY_CREATE_REQUEST["name"]

    def test_get_api_key_not_found(self, test_client: TestClient, auth_headers: dict):
        """Test getting non-existent API key returns 404."""
        agent_id = self._create_agent(test_client, auth_headers)

        response = test_client.get(
            f"/agents/{agent_id}/api-keys/non-existent-key",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_update_api_key(self, test_client: TestClient, auth_headers: dict):
        """Test updating an API key."""
        agent_id = self._create_agent(test_client, auth_headers)

        create_response = test_client.post(
            f"/agents/{agent_id}/api-keys",
            json=API_KEY_CREATE_REQUEST,
            headers=auth_headers,
        )
        key_id = create_response.json()["key_id"]

        response = test_client.patch(
            f"/agents/{agent_id}/api-keys/{key_id}",
            json={"name": "Updated Name", "is_active": False},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["is_active"] is False
        # Allowed origins unchanged
        assert data["allowed_origins"] == API_KEY_CREATE_REQUEST["allowed_origins"]

    def test_update_api_key_not_found(self, test_client: TestClient, auth_headers: dict):
        """Test updating non-existent API key returns 404."""
        agent_id = self._create_agent(test_client, auth_headers)

        response = test_client.patch(
            f"/agents/{agent_id}/api-keys/non-existent-key",
            json={"name": "New Name"},
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_delete_api_key(self, test_client: TestClient, auth_headers: dict):
        """Test deleting an API key."""
        agent_id = self._create_agent(test_client, auth_headers)

        create_response = test_client.post(
            f"/agents/{agent_id}/api-keys",
            json=API_KEY_CREATE_REQUEST,
            headers=auth_headers,
        )
        key_id = create_response.json()["key_id"]

        response = test_client.delete(
            f"/agents/{agent_id}/api-keys/{key_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify key is deleted
        get_response = test_client.get(
            f"/agents/{agent_id}/api-keys/{key_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404

    def test_delete_api_key_idempotent(self, test_client: TestClient, auth_headers: dict):
        """Test deleting non-existent API key still returns success."""
        agent_id = self._create_agent(test_client, auth_headers)

        response = test_client.delete(
            f"/agents/{agent_id}/api-keys/non-existent-key",
            headers=auth_headers,
        )

        assert response.status_code == 204
