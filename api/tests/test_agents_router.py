"""
Tests for agents router endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from tests.mock_data import (
    TEST_USER_EMAIL,
    AGENT_CREATE_REQUEST,
)


class TestAgentsRouter:
    """Tests for agents router happy paths."""

    def test_create_agent_success(self, test_client: TestClient, auth_headers: dict):
        """Test creating a new agent."""
        response = test_client.post(
            "/agents",
            json=AGENT_CREATE_REQUEST,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["agent_name"] == AGENT_CREATE_REQUEST["agent_name"]
        assert data["agent_provider"] == AGENT_CREATE_REQUEST["agent_provider"]
        assert data["agent_persona"] == AGENT_CREATE_REQUEST["agent_persona"]
        assert data["created_by"] == TEST_USER_EMAIL
        assert "agent_id" in data
        # API key should NOT be in response
        assert "agent_provider_api_key" not in data

    def test_create_agent_idempotent(self, test_client: TestClient, auth_headers: dict):
        """Test that creating the same agent twice returns the existing agent."""
        # Create agent first time
        response1 = test_client.post(
            "/agents",
            json=AGENT_CREATE_REQUEST,
            headers=auth_headers,
        )
        assert response1.status_code == 201
        agent_id_1 = response1.json()["agent_id"]

        # Create agent second time with same name
        response2 = test_client.post(
            "/agents",
            json=AGENT_CREATE_REQUEST,
            headers=auth_headers,
        )
        # Should return the existing agent
        assert response2.status_code == 201
        agent_id_2 = response2.json()["agent_id"]

        # Should be the same agent
        assert agent_id_1 == agent_id_2

    def test_create_agent_requires_auth(self, test_client: TestClient):
        """Test that creating an agent requires authentication."""
        response = test_client.post(
            "/agents",
            json=AGENT_CREATE_REQUEST,
        )

        assert response.status_code == 401

    def test_list_agents(self, test_client: TestClient, auth_headers: dict):
        """Test listing all agents for a user."""
        # Create an agent first
        test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=auth_headers)

        response = test_client.get("/agents", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["agent_name"] == AGENT_CREATE_REQUEST["agent_name"]

    def test_get_agent_by_id(self, test_client: TestClient, auth_headers: dict):
        """Test getting a single agent by ID."""
        # Create an agent first
        create_response = test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=auth_headers)
        agent_id = create_response.json()["agent_id"]

        response = test_client.get(f"/agents/{agent_id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == agent_id
        assert data["agent_name"] == AGENT_CREATE_REQUEST["agent_name"]

    def test_get_agent_not_found(self, test_client: TestClient, auth_headers: dict):
        """Test getting a non-existent agent returns 404."""
        response = test_client.get("/agents/non-existent-id", headers=auth_headers)

        assert response.status_code == 404

    def test_get_update_schema(self, test_client: TestClient, auth_headers: dict):
        """Test getting the update form schema."""
        response = test_client.get("/agents/update-schema/test-id", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["form_name"] == "Update Agent Form"
        assert data["submit_path"] == "/agents/test-id"
        # Update schema should not have agent_name field
        field_names = [f["name"] for f in data["form_inputs"]]
        assert "agent_name" not in field_names
        assert "agent_persona" in field_names

    def test_update_agent(self, test_client: TestClient, auth_headers: dict):
        """Test updating an agent."""
        # Create an agent first
        create_response = test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=auth_headers)
        agent_id = create_response.json()["agent_id"]

        # Update the agent
        update_data = {"agent_persona": "Updated persona"}
        response = test_client.put(f"/agents/{agent_id}", json=update_data, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["agent_persona"] == "Updated persona"
        assert data["agent_name"] == AGENT_CREATE_REQUEST["agent_name"]  # Name unchanged

    def test_update_agent_not_found(self, test_client: TestClient, auth_headers: dict):
        """Test updating a non-existent agent returns 404."""
        response = test_client.put(
            "/agents/non-existent-id",
            json={"agent_persona": "New persona"},
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_delete_agent(self, test_client: TestClient, auth_headers: dict):
        """Test deleting an agent."""
        # Create an agent first
        create_response = test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=auth_headers)
        agent_id = create_response.json()["agent_id"]

        # Delete the agent
        response = test_client.delete(f"/agents/{agent_id}", headers=auth_headers)

        assert response.status_code == 204

        # Verify agent is deleted
        get_response = test_client.get(f"/agents/{agent_id}", headers=auth_headers)
        assert get_response.status_code == 404

    def test_delete_agent_idempotent(self, test_client: TestClient, auth_headers: dict):
        """Test deleting a non-existent agent still returns success (idempotent)."""
        response = test_client.delete("/agents/non-existent-id", headers=auth_headers)

        assert response.status_code == 204
