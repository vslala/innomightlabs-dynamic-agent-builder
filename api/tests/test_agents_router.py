"""
Tests for agents router endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from src.agents.turns.models import ConversationTurn, ConversationTurnStatus
from src.agents.turns.repository import ConversationTurnRepository
from src.llm.events import SSEEvent, SSEEventType
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from src.config.settings import DEFAULT_OPENAI_MODELS
from tests.mock_data import (
    TEST_USER_EMAIL,
    AGENT_CREATE_REQUEST,
    CONVERSATION_CREATE_REQUEST,
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

    def test_get_create_schema_hydrates_common_option_sources(
        self,
        test_client: TestClient,
        auth_headers: dict,
    ):
        """Test create form uses the common hydrated option-source contract."""
        response = test_client.get("/agents/supported-models", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["form_name"] == "Create Agent Form"
        provider_field = next(field for field in data["form_inputs"] if field["name"] == "agent_provider")
        model_field = next(field for field in data["form_inputs"] if field["name"] == "agent_model")

        assert provider_field["options_source"] == {
            "type": "agent_model_providers",
            "mode": "hydrate",
        }
        assert model_field["options_source"] == {
            "type": "agent_models",
            "mode": "hydrate",
        }
        assert model_field["input_type"] == "search"
        assert provider_field["options"] == [{"value": "Bedrock", "label": "Bedrock"}]
        assert model_field["options"]

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
        provider_field = next(field for field in data["form_inputs"] if field["name"] == "agent_provider")
        model_field = next(field for field in data["form_inputs"] if field["name"] == "agent_model")
        assert provider_field["options_source"] == {
            "type": "agent_model_providers",
            "mode": "hydrate",
        }
        assert model_field["options_source"] == {
            "type": "agent_models",
            "mode": "hydrate",
        }
        assert model_field["input_type"] == "search"
        assert provider_field["options"] == [{"value": "Bedrock", "label": "Bedrock"}]
        assert model_field["options"]

    def test_update_schema_includes_openai_models_when_connected(
        self,
        test_client: TestClient,
        auth_headers: dict,
        dynamodb_table,
        monkeypatch,
    ):
        """Test OpenAI model options are loaded from shared settings for edit forms."""
        del dynamodb_table
        from src.llm import models as llm_models

        monkeypatch.setattr(llm_models.settings, "openai_models", DEFAULT_OPENAI_MODELS.copy())
        repo = ProviderSettingsRepository()
        repo.save(
            ProviderSettings(
                user_email=TEST_USER_EMAIL,
                provider_name="OpenAI",
                encrypted_credentials="encrypted",
                auth_type="oauth",
            )
        )

        response = test_client.get("/agents/update-schema/test-id", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        provider_field = next(field for field in data["form_inputs"] if field["name"] == "agent_provider")
        model_field = next(field for field in data["form_inputs"] if field["name"] == "agent_model")
        model_values = [option["value"] for option in model_field["options"]]
        openai_start = model_values.index("gpt-5.5")

        assert "OpenAI" in [option["value"] for option in provider_field["options"]]
        assert model_values[openai_start:openai_start + 4] == [
            "gpt-5.5",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.4-nano",
        ]

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

    def test_get_agent2agent_sharing_defaults(self, test_client: TestClient, auth_headers: dict):
        """Test A2A sharing settings default to disabled."""
        create_response = test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=auth_headers)
        agent_id = create_response.json()["agent_id"]

        response = test_client.get(f"/agents/{agent_id}/a2a-sharing", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == agent_id
        assert data["enabled"] is False
        assert data["has_active_api_key"] is False
        assert data["agent_card_url"].endswith(f"/a2a/agents/{agent_id}/card")
        assert data["service_url"].endswith(f"/a2a/agents/{agent_id}")

    def test_enable_agent2agent_sharing_requires_active_api_key(
        self,
        test_client: TestClient,
        auth_headers: dict,
    ):
        """Test enabling A2A sharing requires an active API key."""
        create_response = test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=auth_headers)
        agent_id = create_response.json()["agent_id"]

        response = test_client.put(
            f"/agents/{agent_id}/a2a-sharing",
            json={"enabled": True},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Create an active API key before enabling Agent2Agent discovery"

    def test_enable_and_disable_agent2agent_sharing(
        self,
        test_client: TestClient,
        auth_headers: dict,
    ):
        """Test enabling and disabling A2A sharing."""
        create_response = test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=auth_headers)
        agent_id = create_response.json()["agent_id"]
        key_response = test_client.post(
            f"/agents/{agent_id}/api-keys",
            json={"name": "A2A Key", "allowed_origins": []},
            headers=auth_headers,
        )
        assert key_response.status_code == 201

        enable_response = test_client.put(
            f"/agents/{agent_id}/a2a-sharing",
            json={"enabled": True},
            headers=auth_headers,
        )

        assert enable_response.status_code == 200
        data = enable_response.json()
        assert data["enabled"] is True
        assert data["has_active_api_key"] is True
        agent_response = test_client.get(f"/agents/{agent_id}", headers=auth_headers)
        assert agent_response.json()["is_agent2agent_enabled"] is True

        disable_response = test_client.put(
            f"/agents/{agent_id}/a2a-sharing",
            json={"enabled": False},
            headers=auth_headers,
        )

        assert disable_response.status_code == 200
        assert disable_response.json()["enabled"] is False

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


class _FastArchitecture:
    """A minimal architecture double: completes a turn in a handful of events."""

    async def handle_message(
        self, agent, conversation, user_message, owner_email, actor_email, actor_id, attachments=None
    ):
        yield SSEEvent(event_type=SSEEventType.USER_MESSAGE_SAVED, content="saved", message_id="user-1")
        yield SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content="hi")
        yield SSEEvent(
            event_type=SSEEventType.ASSISTANT_MESSAGE_SAVED, content="saved", message_id="assistant-1"
        )
        yield SSEEvent(event_type=SSEEventType.STREAM_COMPLETE, content="done")


class TestChatTurnEndpoints:
    """Durable chat turns: the X-Turn-Id contract, the concurrency guard, and the
    tail/stop endpoints' ownership checks. See api/docs/LLD-async-chat-turns.md."""

    def _create_agent_and_conversation(
        self, test_client: TestClient, auth_headers: dict, agent_name: str = "Test Agent"
    ) -> tuple[str, str]:
        agent_response = test_client.post(
            "/agents",
            json={**AGENT_CREATE_REQUEST, "agent_name": agent_name},
            headers=auth_headers,
        )
        agent_id = agent_response.json()["agent_id"]
        return agent_id, self._create_conversation(test_client, auth_headers, agent_id)

    def _create_conversation(self, test_client: TestClient, auth_headers: dict, agent_id: str) -> str:
        conversation_response = test_client.post(
            "/conversations/",
            json={**CONVERSATION_CREATE_REQUEST, "agent_id": agent_id},
            headers=auth_headers,
        )
        return conversation_response.json()["conversation_id"]

    def test_send_message_response_carries_turn_id_header(
        self, test_client: TestClient, auth_headers: dict, monkeypatch
    ):
        monkeypatch.setattr(
            "src.agents.turns.run.get_agent_architecture", lambda *_a, **_kw: _FastArchitecture()
        )
        agent_id, conversation_id = self._create_agent_and_conversation(test_client, auth_headers)

        with test_client.stream(
            "POST",
            f"/agents/{agent_id}/{conversation_id}/send-message",
            json={"content": "Hello"},
            headers=auth_headers,
        ) as response:
            assert response.status_code == 200
            assert response.headers.get("X-Turn-Id")
            for _ in response.iter_lines():
                break

    def test_send_message_conflicts_with_running_turn(self, test_client: TestClient, auth_headers: dict):
        agent_id, conversation_id = self._create_agent_and_conversation(test_client, auth_headers)
        active_turn = ConversationTurn(
            conversation_id=conversation_id, agent_id=agent_id, created_by=TEST_USER_EMAIL
        )
        ConversationTurnRepository().create(active_turn)

        response = test_client.post(
            f"/agents/{agent_id}/{conversation_id}/send-message",
            json={"content": "Hello again"},
            headers=auth_headers,
        )

        assert response.status_code == 409
        assert response.json()["detail"]["turn_id"] == active_turn.turn_id

    def test_get_active_turn_returns_null_when_idle_and_turn_when_running(
        self, test_client: TestClient, auth_headers: dict
    ):
        agent_id, conversation_id = self._create_agent_and_conversation(test_client, auth_headers)

        idle_response = test_client.get(
            f"/agents/{agent_id}/{conversation_id}/turns/active", headers=auth_headers
        )
        assert idle_response.status_code == 200
        assert idle_response.json() is None

        active_turn = ConversationTurn(
            conversation_id=conversation_id, agent_id=agent_id, created_by=TEST_USER_EMAIL
        )
        ConversationTurnRepository().create(active_turn)

        running_response = test_client.get(
            f"/agents/{agent_id}/{conversation_id}/turns/active", headers=auth_headers
        )
        assert running_response.status_code == 200
        assert running_response.json()["turn_id"] == active_turn.turn_id

    def test_stream_turn_events_404_for_mismatched_conversation(
        self, test_client: TestClient, auth_headers: dict
    ):
        agent_id, conversation_a = self._create_agent_and_conversation(test_client, auth_headers)
        conversation_b = self._create_conversation(test_client, auth_headers, agent_id)
        turn_b = ConversationTurn(
            conversation_id=conversation_b, agent_id=agent_id, created_by=TEST_USER_EMAIL
        )
        ConversationTurnRepository().create(turn_b)

        response = test_client.get(
            f"/agents/{agent_id}/{conversation_a}/turns/{turn_b.turn_id}/events", headers=auth_headers
        )

        assert response.status_code == 404

    def test_stream_turn_events_410_when_transcript_not_live(
        self, test_client: TestClient, auth_headers: dict
    ):
        agent_id, conversation_id = self._create_agent_and_conversation(test_client, auth_headers)
        finished_turn = ConversationTurn(
            conversation_id=conversation_id,
            agent_id=agent_id,
            created_by=TEST_USER_EMAIL,
            status=ConversationTurnStatus.SUCCEEDED,
        )
        ConversationTurnRepository().create(finished_turn)

        response = test_client.get(
            f"/agents/{agent_id}/{conversation_id}/turns/{finished_turn.turn_id}/events", headers=auth_headers
        )

        assert response.status_code == 410

    def test_stop_turn_404_for_mismatched_conversation(self, test_client: TestClient, auth_headers: dict):
        agent_id, conversation_a = self._create_agent_and_conversation(test_client, auth_headers)
        conversation_b = self._create_conversation(test_client, auth_headers, agent_id)
        turn_b = ConversationTurn(
            conversation_id=conversation_b, agent_id=agent_id, created_by=TEST_USER_EMAIL
        )
        ConversationTurnRepository().create(turn_b)

        response = test_client.post(
            f"/agents/{agent_id}/{conversation_a}/turns/{turn_b.turn_id}/stop", headers=auth_headers
        )

        assert response.status_code == 404
