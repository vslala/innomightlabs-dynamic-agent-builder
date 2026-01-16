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

    def test_get_supported_models_schema(self, test_client: TestClient, auth_headers: dict):
        """Test getting the form schema for creating agents."""
        response = test_client.get(
            "/agents/supported-models",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["form_name"] == "Create Agent Form"
        assert "form_inputs" in data
        assert len(data["form_inputs"]) == 4

    def test_create_agent_requires_auth(self, test_client: TestClient):
        """Test that creating an agent requires authentication."""
        response = test_client.post(
            "/agents",
            json=AGENT_CREATE_REQUEST,
        )

        assert response.status_code == 401
