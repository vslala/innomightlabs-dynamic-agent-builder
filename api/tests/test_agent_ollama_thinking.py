"""Per-agent Ollama thinking-mode choice: model, form schema, and the API round trip."""

from fastapi.testclient import TestClient

from src.agents.models import Agent
from src.agents.schemas import UPDATE_AGENT_FORM
from tests.mock_data import AGENT_CREATE_REQUEST, TEST_USER_EMAIL


class TestAgentModel:
    def test_new_agents_default_to_no_stored_preference(self):
        agent = Agent(
            agent_name="A",
            agent_architecture="krishna-mini",
            agent_provider="Ollama",
            agent_persona="p",
            created_by=TEST_USER_EMAIL,
        )

        assert agent.agent_ollama_thinking is None

    def test_response_normalizes_an_unset_preference_to_default(self):
        agent = Agent(
            agent_name="A",
            agent_architecture="krishna-mini",
            agent_provider="Ollama",
            agent_persona="p",
            created_by=TEST_USER_EMAIL,
        )

        assert agent.to_response().agent_ollama_thinking == "default"

    def test_response_preserves_an_explicit_preference(self):
        agent = Agent(
            agent_name="A",
            agent_architecture="krishna-mini",
            agent_provider="Ollama",
            agent_persona="p",
            agent_ollama_thinking="enabled",
            created_by=TEST_USER_EMAIL,
        )

        assert agent.to_response().agent_ollama_thinking == "enabled"

    def test_round_trips_through_dynamo_item_conversion(self):
        agent = Agent(
            agent_name="A",
            agent_architecture="krishna-mini",
            agent_provider="Ollama",
            agent_persona="p",
            agent_ollama_thinking="disabled",
            created_by=TEST_USER_EMAIL,
        )

        restored = Agent.from_dynamo_item(agent.to_dynamo_item())

        assert restored.agent_ollama_thinking == "disabled"

    def test_a_pre_existing_dynamo_item_without_the_field_loads_as_unset(self):
        agent = Agent(
            agent_name="A",
            agent_architecture="krishna-mini",
            agent_provider="Bedrock",
            agent_persona="p",
            created_by=TEST_USER_EMAIL,
        )
        item = agent.to_dynamo_item()
        del item["agent_ollama_thinking"]

        restored = Agent.from_dynamo_item(item)

        assert restored.agent_ollama_thinking is None


class TestUpdateAgentFormSchema:
    def test_the_field_is_declared_optional(self):
        field = next(f for f in UPDATE_AGENT_FORM.form_inputs if f.name == "agent_ollama_thinking")

        assert field.is_optional is True

    def test_the_field_offers_exactly_the_three_documented_choices(self):
        field = next(f for f in UPDATE_AGENT_FORM.form_inputs if f.name == "agent_ollama_thinking")

        assert {option.value for option in field.options} == {"default", "enabled", "disabled"}


class TestAgentRouterRoundTrip:
    def test_create_agent_persists_the_chosen_thinking_mode(
        self, test_client: TestClient, auth_headers: dict
    ):
        response = test_client.post(
            "/agents",
            json={**AGENT_CREATE_REQUEST, "agent_provider": "Ollama", "agent_ollama_thinking": "enabled"},
            headers=auth_headers,
        )

        assert response.status_code == 201
        assert response.json()["agent_ollama_thinking"] == "enabled"

    def test_create_agent_without_a_choice_reports_the_default(
        self, test_client: TestClient, auth_headers: dict
    ):
        response = test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=auth_headers)

        assert response.status_code == 201
        assert response.json()["agent_ollama_thinking"] == "default"

    def test_update_agent_changes_the_thinking_mode(self, test_client: TestClient, auth_headers: dict):
        agent_id = test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=auth_headers).json()["agent_id"]

        response = test_client.put(
            f"/agents/{agent_id}",
            json={"agent_ollama_thinking": "disabled"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["agent_ollama_thinking"] == "disabled"

    def test_update_agent_can_reset_back_to_the_provider_default(
        self, test_client: TestClient, auth_headers: dict
    ):
        agent_id = test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=auth_headers).json()["agent_id"]
        test_client.put(f"/agents/{agent_id}", json={"agent_ollama_thinking": "enabled"}, headers=auth_headers)

        response = test_client.put(
            f"/agents/{agent_id}",
            json={"agent_ollama_thinking": "default"},
            headers=auth_headers,
        )

        assert response.json()["agent_ollama_thinking"] == "default"
