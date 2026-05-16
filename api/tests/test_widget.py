"""
Tests for Widget module.
"""

import pytest
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
import jwt
from fastapi.testclient import TestClient

from tests.mock_data import (
    TEST_USER_EMAIL,
    AGENT_CREATE_REQUEST,
)

# API key with empty allowed_origins for testing (allows any origin)
WIDGET_API_KEY_REQUEST = {
    "name": "Widget Test Key",
    "allowed_origins": [],  # Empty = allow all origins
}


class TestWidgetConversationModel:
    """Tests for WidgetConversation model."""

    def test_widget_conversation_defaults(self, dynamodb_table):
        """Test WidgetConversation model default values."""
        from src.widget.models import WidgetConversation

        conversation = WidgetConversation(
            agent_id="agent-123",
            visitor_id="visitor-456",
            visitor_email="visitor@example.com",
        )

        assert conversation.conversation_id  # UUID generated
        assert conversation.title == "New Conversation"
        assert conversation.message_count == 0
        assert conversation.visitor_name is None

    def test_widget_conversation_pk_sk_format(self, dynamodb_table):
        """Test partition key and sort key format."""
        from src.widget.models import WidgetConversation

        conversation = WidgetConversation(
            agent_id="agent-123",
            visitor_id="visitor-456",
            visitor_email="visitor@example.com",
        )

        assert conversation.pk == "Agent#agent-123#Widget"
        assert conversation.sk.startswith("Conversation#")

    def test_widget_conversation_gsi2_keys(self, dynamodb_table):
        """Test GSI2 key format for visitor lookup."""
        from src.widget.models import WidgetConversation

        conversation = WidgetConversation(
            agent_id="agent-123",
            visitor_id="visitor-456",
            visitor_email="visitor@example.com",
        )

        assert conversation.gsi2_pk == "Visitor#visitor-456"
        assert conversation.gsi2_sk.startswith("Agent#agent-123#Conversation#")


class TestWidgetConversationRepository:
    """Tests for WidgetConversationRepository."""

    def test_save_creates_new_conversation(self, dynamodb_table):
        """Test saving a new widget conversation."""
        from src.widget.models import WidgetConversation
        from src.widget.repository import WidgetConversationRepository

        repo = WidgetConversationRepository()
        conversation = WidgetConversation(
            agent_id="agent-123",
            visitor_id="visitor-456",
            visitor_email="visitor@example.com",
            title="Test Chat",
        )

        saved = repo.save(conversation)

        assert saved.conversation_id == conversation.conversation_id
        assert saved.title == "Test Chat"

    def test_find_by_id(self, dynamodb_table):
        """Test finding widget conversation by ID."""
        from src.widget.models import WidgetConversation
        from src.widget.repository import WidgetConversationRepository

        repo = WidgetConversationRepository()
        conversation = WidgetConversation(
            agent_id="agent-123",
            visitor_id="visitor-456",
            visitor_email="visitor@example.com",
        )
        repo.save(conversation)

        found = repo.find_by_id("agent-123", conversation.conversation_id)

        assert found is not None
        assert found.conversation_id == conversation.conversation_id

    def test_find_by_id_not_found(self, dynamodb_table):
        """Test finding non-existent conversation returns None."""
        from src.widget.repository import WidgetConversationRepository

        repo = WidgetConversationRepository()
        found = repo.find_by_id("agent-123", "non-existent")

        assert found is None

    def test_find_by_visitor_and_agent(self, dynamodb_table):
        """Test finding conversations for a visitor with specific agent."""
        from src.widget.models import WidgetConversation
        from src.widget.repository import WidgetConversationRepository

        repo = WidgetConversationRepository()

        # Create conversations for same visitor with different agents
        for i in range(3):
            conv = WidgetConversation(
                agent_id="agent-123",
                visitor_id="visitor-456",
                visitor_email="visitor@example.com",
                title=f"Chat {i}",
            )
            repo.save(conv)

        # Create conversation with different agent
        other_conv = WidgetConversation(
            agent_id="agent-789",
            visitor_id="visitor-456",
            visitor_email="visitor@example.com",
        )
        repo.save(other_conv)

        conversations = repo.find_by_visitor_and_agent("visitor-456", "agent-123")

        assert len(conversations) == 3
        assert all(c.agent_id == "agent-123" for c in conversations)

    def test_delete_by_id(self, dynamodb_table):
        """Test deleting a widget conversation."""
        from src.widget.models import WidgetConversation
        from src.widget.repository import WidgetConversationRepository

        repo = WidgetConversationRepository()
        conversation = WidgetConversation(
            agent_id="agent-123",
            visitor_id="visitor-456",
            visitor_email="visitor@example.com",
        )
        repo.save(conversation)

        result = repo.delete_by_id("agent-123", conversation.conversation_id)

        assert result is True
        assert repo.find_by_id("agent-123", conversation.conversation_id) is None


class TestWidgetMiddleware:
    """Tests for widget authentication middleware."""

    def test_is_origin_allowed_empty_list(self, dynamodb_table):
        """Test origin validation with empty allowed_origins."""
        from src.apikeys.models import AgentApiKey

        api_key = AgentApiKey(
            agent_id="agent-123",
            name="Test Key",
            allowed_origins=[],
            created_by=TEST_USER_EMAIL,
        )

        assert api_key.is_origin_allowed("https://any-site.com") is True
        assert api_key.is_origin_allowed(None) is True

    def test_is_origin_allowed_with_list(self, dynamodb_table):
        """Test origin validation with specified allowed_origins."""
        from src.apikeys.models import AgentApiKey

        api_key = AgentApiKey(
            agent_id="agent-123",
            name="Test Key",
            allowed_origins=["https://allowed.com"],
            created_by=TEST_USER_EMAIL,
        )

        assert api_key.is_origin_allowed("https://allowed.com") is True
        assert api_key.is_origin_allowed("https://blocked.com") is False


class TestWidgetRouter:
    """Tests for widget router endpoints."""

    def _create_agent_and_api_key(
        self, test_client: TestClient, auth_headers: dict
    ) -> tuple[str, str]:
        """Helper to create an agent and API key, returns (agent_id, public_key)."""
        # Create agent
        response = test_client.post(
            "/agents",
            json=AGENT_CREATE_REQUEST,
            headers=auth_headers,
        )
        agent_id = response.json()["agent_id"]

        # Create API key with empty allowed_origins (allows any origin)
        response = test_client.post(
            f"/agents/{agent_id}/api-keys",
            json=WIDGET_API_KEY_REQUEST,
            headers=auth_headers,
        )
        public_key = response.json()["public_key"]

        return agent_id, public_key

    def _create_visitor_token(self, visitor_id: str, agent_id: str) -> str:
        """Helper to create a visitor JWT token."""
        payload = {
            "sub": visitor_id,
            "email": "visitor@example.com",
            "name": "Test Visitor",
            "picture": None,
            "agent_id": agent_id,
            "type": "widget_visitor",
            "exp": datetime.now(timezone.utc) + timedelta(hours=4),
            "iat": datetime.now(timezone.utc),
        }
        return jwt.encode(payload, "test-secret", algorithm="HS256")

    def test_widget_config_requires_api_key(self, test_client: TestClient, auth_headers: dict):
        """Test that widget config requires X-API-Key header."""
        response = test_client.get("/widget/config")
        assert response.status_code == 401
        assert "X-API-Key" in response.json()["detail"]

    def test_widget_config_with_valid_api_key(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test getting widget config with valid API key."""
        agent_id, public_key = self._create_agent_and_api_key(test_client, auth_headers)

        response = test_client.get(
            "/widget/config",
            headers={"X-API-Key": public_key},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == agent_id

    def test_widget_config_with_invalid_api_key(self, test_client: TestClient):
        """Test widget config with invalid API key returns 401."""
        response = test_client.get(
            "/widget/config",
            headers={"X-API-Key": "pk_live_invalid"},
        )

        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    def test_widget_oauth_callback_redirect_includes_refresh_token(
        self,
        test_client: TestClient,
        auth_headers: dict,
        monkeypatch,
    ):
        """OAuth callback redirects with widget JWT and Google refresh token."""
        _, public_key = self._create_agent_and_api_key(test_client, auth_headers)

        async def fake_exchange_code_for_tokens(code: str, redirect_uri: str | None = None):
            assert code == "code-123"
            assert redirect_uri == "http://testserver/widget/auth/callback"
            return {
                "access_token": "google-access-token",
                "refresh_token": "google-refresh-token",
            }

        async def fake_get_user_info(access_token: str):
            assert access_token == "google-access-token"
            return {
                "id": "google-user-123",
                "email": "visitor@example.com",
                "name": "Test Visitor",
                "picture": "https://example.com/avatar.png",
            }

        import src.widget.router as widget_router

        monkeypatch.setattr(
            widget_router.google_oauth,
            "exchange_code_for_tokens",
            fake_exchange_code_for_tokens,
        )
        monkeypatch.setattr(
            widget_router.google_oauth,
            "get_user_info",
            fake_get_user_info,
        )

        response = test_client.get(
            "/widget/auth/callback",
            params={
                "code": "code-123",
                "state": f"{public_key}|vscode://innomightlabs/auth-callback",
            },
            follow_redirects=False,
        )

        assert response.status_code == 307
        location = response.headers["location"]
        parsed = urlparse(location)
        params = parse_qs(parsed.query)
        assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "vscode://innomightlabs/auth-callback"
        assert params["refresh_token"] == ["google-refresh-token"]
        assert params["visitor_id"] == ["google-user-123"]
        assert params["email"] == ["visitor@example.com"]
        assert params["token"][0]

    def test_refresh_widget_token_returns_new_access_token_and_refresh_token(
        self,
        test_client: TestClient,
        auth_headers: dict,
        monkeypatch,
    ):
        """Refresh endpoint exchanges Google refresh token for a new widget JWT."""
        agent_id, public_key = self._create_agent_and_api_key(test_client, auth_headers)

        async def fake_refresh_access_token(refresh_token: str):
            assert refresh_token == "google-refresh-token"
            return {"access_token": "new-google-access-token"}

        async def fake_get_user_info(access_token: str):
            assert access_token == "new-google-access-token"
            return {
                "id": "google-user-123",
                "email": "visitor@example.com",
                "name": "Test Visitor",
                "picture": None,
            }

        import src.widget.router as widget_router

        monkeypatch.setattr(
            widget_router.google_oauth,
            "refresh_access_token",
            fake_refresh_access_token,
        )
        monkeypatch.setattr(
            widget_router.google_oauth,
            "get_user_info",
            fake_get_user_info,
        )

        response = test_client.post(
            "/widget/auth/refresh",
            json={"refresh_token": "google-refresh-token"},
            headers={"X-API-Key": public_key},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["refresh_token"] == "google-refresh-token"
        assert data["expires_in"] == 4 * 3600
        assert data["visitor"]["visitor_id"] == "google-user-123"
        payload = jwt.decode(data["access_token"], "test-secret", algorithms=["HS256"])
        assert payload["sub"] == "google-user-123"
        assert payload["email"] == "visitor@example.com"
        assert payload["agent_id"] == agent_id
        assert payload["type"] == "widget_visitor"

    def test_refresh_widget_token_requires_api_key(self, test_client: TestClient):
        """Refresh endpoint still requires a valid widget API key."""
        response = test_client.post(
            "/widget/auth/refresh",
            json={"refresh_token": "google-refresh-token"},
        )

        assert response.status_code == 401
        assert "X-API-Key" in response.json()["detail"]

    def test_create_widget_conversation(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test creating a widget conversation."""
        agent_id, public_key = self._create_agent_and_api_key(test_client, auth_headers)
        visitor_token = self._create_visitor_token("visitor-123", agent_id)

        response = test_client.post(
            "/widget/conversations",
            json={"title": "Test Chat"},
            headers={
                "X-API-Key": public_key,
                "Authorization": f"Bearer {visitor_token}",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Chat"
        assert data["agent_id"] == agent_id
        assert data["visitor_id"] == "visitor-123"

    def test_create_widget_conversation_requires_visitor_token(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test that creating conversation requires visitor token."""
        agent_id, public_key = self._create_agent_and_api_key(test_client, auth_headers)

        response = test_client.post(
            "/widget/conversations",
            json={"title": "Test Chat"},
            headers={"X-API-Key": public_key},
        )

        assert response.status_code == 401

    def test_list_widget_conversations(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test listing widget conversations for a visitor."""
        agent_id, public_key = self._create_agent_and_api_key(test_client, auth_headers)
        visitor_token = self._create_visitor_token("visitor-123", agent_id)
        headers = {
            "X-API-Key": public_key,
            "Authorization": f"Bearer {visitor_token}",
        }

        # Create two conversations
        test_client.post("/widget/conversations", json={"title": "Chat 1"}, headers=headers)
        test_client.post("/widget/conversations", json={"title": "Chat 2"}, headers=headers)

        response = test_client.get("/widget/conversations", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_get_widget_conversation(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test getting a specific widget conversation."""
        agent_id, public_key = self._create_agent_and_api_key(test_client, auth_headers)
        visitor_token = self._create_visitor_token("visitor-123", agent_id)
        headers = {
            "X-API-Key": public_key,
            "Authorization": f"Bearer {visitor_token}",
        }

        # Create conversation
        create_response = test_client.post(
            "/widget/conversations",
            json={"title": "My Chat"},
            headers=headers,
        )
        conversation_id = create_response.json()["conversation_id"]

        response = test_client.get(
            f"/widget/conversations/{conversation_id}",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["conversation_id"] == conversation_id
        assert data["title"] == "My Chat"

    def test_get_widget_conversation_access_denied(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test that visitors cannot access other visitors' conversations."""
        agent_id, public_key = self._create_agent_and_api_key(test_client, auth_headers)

        # Create conversation as visitor-1
        visitor1_token = self._create_visitor_token("visitor-1", agent_id)
        create_response = test_client.post(
            "/widget/conversations",
            json={"title": "Visitor 1 Chat"},
            headers={
                "X-API-Key": public_key,
                "Authorization": f"Bearer {visitor1_token}",
            },
        )
        conversation_id = create_response.json()["conversation_id"]

        # Try to access as visitor-2
        visitor2_token = self._create_visitor_token("visitor-2", agent_id)
        response = test_client.get(
            f"/widget/conversations/{conversation_id}",
            headers={
                "X-API-Key": public_key,
                "Authorization": f"Bearer {visitor2_token}",
            },
        )

        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

    def test_widget_conversation_not_found(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test getting non-existent conversation returns 404."""
        agent_id, public_key = self._create_agent_and_api_key(test_client, auth_headers)
        visitor_token = self._create_visitor_token("visitor-123", agent_id)

        response = test_client.get(
            "/widget/conversations/non-existent-id",
            headers={
                "X-API-Key": public_key,
                "Authorization": f"Bearer {visitor_token}",
            },
        )

        assert response.status_code == 404

    def test_oauth_callback_page_returns_html(self, test_client: TestClient):
        """Test that the OAuth callback page endpoint returns HTML."""
        response = test_client.get("/widget/auth/callback-page")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "innomight-oauth-callback" in response.text
        assert "postMessage" in response.text

    def test_widget_send_message_uses_owner_provider_credentials(
        self,
        test_client: TestClient,
        auth_headers: dict,
        monkeypatch,
    ):
        """Widget chats must load provider credentials from the agent owner, not the visitor."""

        agent_id, public_key = self._create_agent_and_api_key(test_client, auth_headers)
        visitor_token = self._create_visitor_token("visitor-123", agent_id)
        headers = {
            "X-API-Key": public_key,
            "Authorization": f"Bearer {visitor_token}",
        }

        # Create a widget conversation
        create_response = test_client.post(
            "/widget/conversations",
            json={"title": "My Chat"},
            headers=headers,
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["conversation_id"]

        # Patch architecture resolution to a fake that captures the call args
        captured: dict = {}

        class FakeArchitecture:
            async def handle_message(self, **kwargs):
                captured.update(kwargs)
                if False:  # pragma: no cover (keeps this as an async generator)
                    yield None

        import src.widget.router as widget_router

        monkeypatch.setattr(
            widget_router,
            "get_agent_architecture",
            lambda _name: FakeArchitecture(),
        )

        # Trigger message send; consume the stream to execute server-side generator
        with test_client.stream(
            "POST",
            f"/widget/conversations/{conversation_id}/messages",
            json={"content": "Hello"},
            headers=headers,
        ) as resp:
            assert resp.status_code == 200
            # Read at least one line to ensure generator runs
            for _ in resp.iter_lines():
                break

        # Owner should be the API key creator; actor should be the visitor
        assert captured["owner_email"] == TEST_USER_EMAIL
        assert captured["actor_email"] == "visitor@example.com"
        assert captured["actor_id"] == "visitor-123"
