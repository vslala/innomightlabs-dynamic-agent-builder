"""
Tests for conversations router endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from tests.mock_data import (
    TEST_USER_EMAIL,
    AGENT_CREATE_REQUEST,
    CONVERSATION_CREATE_REQUEST,
    CONVERSATION_CREATE_REQUEST_2,
)


class TestConversationsRouter:
    """Tests for conversations router."""

    @pytest.fixture(autouse=True)
    def setup_agent(self, test_client: TestClient, auth_headers: dict):
        """Create an agent before each test since conversations require agents."""
        response = test_client.post(
            "/agents", json=AGENT_CREATE_REQUEST, headers=auth_headers
        )
        self.agent_id = response.json()["agent_id"]

    def test_create_conversation_success(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test creating a new conversation."""
        request_data = {
            **CONVERSATION_CREATE_REQUEST,
            "agent_id": self.agent_id,
        }
        response = test_client.post(
            "/conversations/", json=request_data, headers=auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == CONVERSATION_CREATE_REQUEST["title"]
        assert data["description"] == CONVERSATION_CREATE_REQUEST["description"]
        assert data["agent_id"] == self.agent_id
        assert data["created_by"] == TEST_USER_EMAIL
        assert "conversation_id" in data

    def test_create_conversation_with_invalid_agent(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test creating a conversation with non-existent agent returns 404."""
        request_data = {
            **CONVERSATION_CREATE_REQUEST,
            "agent_id": "non-existent-agent-id",
        }
        response = test_client.post(
            "/conversations/", json=request_data, headers=auth_headers
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_create_conversation_requires_auth(self, test_client: TestClient):
        """Test that creating a conversation requires authentication."""
        response = test_client.post(
            "/conversations/", json=CONVERSATION_CREATE_REQUEST
        )

        assert response.status_code == 401

    def test_list_conversations(self, test_client: TestClient, auth_headers: dict):
        """Test listing all conversations for a user."""
        # Create a conversation first
        request_data = {**CONVERSATION_CREATE_REQUEST, "agent_id": self.agent_id}
        test_client.post("/conversations/", json=request_data, headers=auth_headers)

        response = test_client.get("/conversations/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "has_more" in data
        assert len(data["items"]) >= 1
        assert data["items"][0]["title"] == CONVERSATION_CREATE_REQUEST["title"]

    def test_list_conversations_pagination(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test paginated conversation listing."""
        # Create 5 conversations
        for i in range(5):
            request_data = {
                "title": f"Conversation {i}",
                "description": f"Description {i}",
                "agent_id": self.agent_id,
            }
            test_client.post("/conversations/", json=request_data, headers=auth_headers)

        # Get first page with limit=2
        response = test_client.get(
            "/conversations/?limit=2", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is True
        assert data["next_cursor"] is not None

        # Get next page
        next_cursor = data["next_cursor"]
        response2 = test_client.get(
            f"/conversations/?limit=2&cursor={next_cursor}", headers=auth_headers
        )

        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["items"]) == 2
        assert data2["has_more"] is True

    def test_get_conversation_by_id(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test getting a single conversation by ID."""
        # Create a conversation first
        request_data = {**CONVERSATION_CREATE_REQUEST, "agent_id": self.agent_id}
        create_response = test_client.post(
            "/conversations/", json=request_data, headers=auth_headers
        )
        conversation_id = create_response.json()["conversation_id"]

        response = test_client.get(
            f"/conversations/{conversation_id}", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["conversation_id"] == conversation_id
        assert data["title"] == CONVERSATION_CREATE_REQUEST["title"]

    def test_get_conversation_not_found(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test getting a non-existent conversation returns 404."""
        response = test_client.get(
            "/conversations/non-existent-id", headers=auth_headers
        )

        assert response.status_code == 404

    def test_update_conversation(self, test_client: TestClient, auth_headers: dict):
        """Test updating a conversation."""
        # Create a conversation first
        request_data = {**CONVERSATION_CREATE_REQUEST, "agent_id": self.agent_id}
        create_response = test_client.post(
            "/conversations/", json=request_data, headers=auth_headers
        )
        conversation_id = create_response.json()["conversation_id"]

        # Update the conversation
        update_data = {
            "title": "Updated Title",
            "description": "Updated description",
        }
        response = test_client.put(
            f"/conversations/{conversation_id}",
            json=update_data,
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["description"] == "Updated description"
        assert data["agent_id"] == self.agent_id  # Unchanged

    def test_update_conversation_agent(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test updating conversation's agent."""
        # Create a second agent
        agent2_request = {
            **AGENT_CREATE_REQUEST,
            "agent_name": "Second Agent",
        }
        agent2_response = test_client.post(
            "/agents", json=agent2_request, headers=auth_headers
        )
        agent2_id = agent2_response.json()["agent_id"]

        # Create a conversation
        request_data = {**CONVERSATION_CREATE_REQUEST, "agent_id": self.agent_id}
        create_response = test_client.post(
            "/conversations/", json=request_data, headers=auth_headers
        )
        conversation_id = create_response.json()["conversation_id"]

        # Update agent
        response = test_client.put(
            f"/conversations/{conversation_id}",
            json={"agent_id": agent2_id},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["agent_id"] == agent2_id

    def test_update_conversation_with_invalid_agent(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test updating conversation with non-existent agent returns 404."""
        # Create a conversation
        request_data = {**CONVERSATION_CREATE_REQUEST, "agent_id": self.agent_id}
        create_response = test_client.post(
            "/conversations/", json=request_data, headers=auth_headers
        )
        conversation_id = create_response.json()["conversation_id"]

        # Try to update with non-existent agent
        response = test_client.put(
            f"/conversations/{conversation_id}",
            json={"agent_id": "non-existent-agent"},
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_update_conversation_not_found(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test updating a non-existent conversation returns 404."""
        response = test_client.put(
            "/conversations/non-existent-id",
            json={"title": "New Title"},
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_delete_conversation(self, test_client: TestClient, auth_headers: dict):
        """Test deleting a conversation."""
        # Create a conversation first
        request_data = {**CONVERSATION_CREATE_REQUEST, "agent_id": self.agent_id}
        create_response = test_client.post(
            "/conversations/", json=request_data, headers=auth_headers
        )
        conversation_id = create_response.json()["conversation_id"]

        # Delete the conversation
        response = test_client.delete(
            f"/conversations/{conversation_id}", headers=auth_headers
        )

        assert response.status_code == 204

        # Verify conversation is deleted
        get_response = test_client.get(
            f"/conversations/{conversation_id}", headers=auth_headers
        )
        assert get_response.status_code == 404

    def test_delete_conversation_not_found(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test deleting a non-existent conversation returns 404."""
        response = test_client.delete(
            "/conversations/non-existent-id", headers=auth_headers
        )

        assert response.status_code == 404
