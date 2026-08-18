from fastapi.testclient import TestClient

from tests.mock_data import AGENT_CREATE_REQUEST


def _create_agent(test_client: TestClient, auth_headers: dict, *, name: str = "A2A Agent") -> str:
    payload = {
        **AGENT_CREATE_REQUEST,
        "agent_name": name,
        "agent_description": "  Helps with   A2A discovery.  ",
        "agent_persona": "SECRET PERSONA SHOULD NOT BE PUBLIC",
    }
    response = test_client.post("/agents", json=payload, headers=auth_headers)
    assert response.status_code == 201
    return str(response.json()["agent_id"])


def _create_api_key(test_client: TestClient, auth_headers: dict, agent_id: str) -> None:
    response = test_client.post(
        f"/agents/{agent_id}/api-keys",
        json={"name": "A2A Key", "allowed_origins": []},
        headers=auth_headers,
    )
    assert response.status_code == 201


def _enable_a2a(test_client: TestClient, auth_headers: dict, agent_id: str) -> None:
    response = test_client.put(
        f"/agents/{agent_id}/a2a-sharing",
        json={"enabled": True},
        headers=auth_headers,
    )
    assert response.status_code == 200


def test_facilitator_agent_card_is_public(test_client: TestClient):
    """Test the well-known facilitator Agent Card is public."""
    response = test_client.get("/.well-known/agent-card.json")

    assert response.status_code == 200
    data = response.json()
    assert data["protocolVersion"] == "1.0.0"
    assert data["name"] == "InnomightLabs A2A Facilitator"
    assert data["url"].endswith("/a2a")
    assert data["securitySchemes"]["agentApiKey"]["in"] == "header"
    assert data["security"] == [{"agentApiKey": []}]


def test_facilitator_card_lists_only_enabled_agents(
    test_client: TestClient,
    auth_headers: dict,
):
    """Test facilitator metadata lists only A2A-enabled agents."""
    from src.agents.models import Agent
    from src.agents.repository import AgentRepository
    from tests.mock_data import TEST_USER_EMAIL

    enabled_agent_id = _create_agent(test_client, auth_headers, name="Enabled Agent")
    disabled_agent = Agent(
        agent_name="Disabled Agent",
        agent_architecture=AGENT_CREATE_REQUEST["agent_architecture"],
        agent_provider=AGENT_CREATE_REQUEST["agent_provider"],
        agent_persona="SECRET PERSONA SHOULD NOT BE PUBLIC",
        agent_description="Disabled description",
        created_by=TEST_USER_EMAIL,
        is_agent2agent_enabled=False,
    )
    AgentRepository().save(disabled_agent)
    _create_api_key(test_client, auth_headers, enabled_agent_id)
    _enable_a2a(test_client, auth_headers, enabled_agent_id)

    response = test_client.get("/.well-known/agent-card.json")

    assert response.status_code == 200
    agents = response.json()["metadata"]["agents"]
    agent_ids = {agent["agent_id"] for agent in agents}
    assert enabled_agent_id in agent_ids
    assert disabled_agent.agent_id not in agent_ids


def test_list_a2a_agents_is_public_and_sanitized(
    test_client: TestClient,
    auth_headers: dict,
):
    """Test public A2A agent summaries are built from safe Agent fields."""
    agent_id = _create_agent(test_client, auth_headers, name="  Public   Agent  ")
    _create_api_key(test_client, auth_headers, agent_id)
    _enable_a2a(test_client, auth_headers, agent_id)

    response = test_client.get("/a2a/agents")

    assert response.status_code == 200
    data = response.json()
    assert data["next_cursor"] is None
    item = next(agent for agent in data["items"] if agent["agent_id"] == agent_id)
    assert item["name"] == "Public Agent"
    assert item["description"] == "Helps with A2A discovery."
    assert item["service_url"].endswith(f"/a2a/agents/{agent_id}")
    assert "SECRET PERSONA" not in response.text


def test_agent_scoped_card_requires_enabled_agent(
    test_client: TestClient,
    auth_headers: dict,
):
    """Test disabled agents do not expose an agent-scoped card."""
    agent_id = _create_agent(test_client, auth_headers)

    response = test_client.get(f"/a2a/agents/{agent_id}/agent-card")

    assert response.status_code == 404


def test_agent_scoped_card_is_public_for_enabled_agent(
    test_client: TestClient,
    auth_headers: dict,
):
    """Test enabled agents expose a sanitized agent-scoped card."""
    agent_id = _create_agent(test_client, auth_headers, name="Public A2A Agent")
    _create_api_key(test_client, auth_headers, agent_id)
    _enable_a2a(test_client, auth_headers, agent_id)

    response = test_client.get(f"/a2a/agents/{agent_id}/agent-card")

    assert response.status_code == 200
    data = response.json()
    assert data["protocolVersion"] == "1.0.0"
    assert data["name"] == "Public A2A Agent"
    assert data["description"] == "Helps with A2A discovery."
    assert data["url"].endswith(f"/a2a/agents/{agent_id}")
    assert data["skills"][0]["id"] == "chat"
    assert "SECRET PERSONA" not in response.text
