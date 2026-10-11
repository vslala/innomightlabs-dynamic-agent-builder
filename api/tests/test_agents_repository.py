"""
Tests for AgentRepository.
"""

import pytest

from src.agents.models import Agent
from tests.mock_data import (
    TEST_USER_EMAIL,
    TEST_USER_EMAIL_2,
    AGENT_CREATE_REQUEST,
    AGENT_CREATE_REQUEST_2,
    agent_fields,
    owner_ids,
)


class TestAgentRepository:
    """Tests for AgentRepository happy paths."""

    def test_save_creates_new_agent(self, agent_repository):
        """Test that save() creates a new agent."""
        agent = Agent(
            agent_name=AGENT_CREATE_REQUEST["agent_name"],
            agent_architecture=AGENT_CREATE_REQUEST["agent_architecture"],
            agent_provider=AGENT_CREATE_REQUEST["agent_provider"],
            agent_provider_api_key=AGENT_CREATE_REQUEST["agent_provider_api_key"],
            agent_persona=AGENT_CREATE_REQUEST["agent_persona"],
            **agent_fields(TEST_USER_EMAIL),
        )

        saved_agent = agent_repository.save(agent)

        assert saved_agent.agent_id == agent.agent_id
        assert saved_agent.agent_name == AGENT_CREATE_REQUEST["agent_name"]
        assert (saved_agent.account_id, saved_agent.owner_id) == owner_ids(TEST_USER_EMAIL)
        assert saved_agent.is_agent2agent_enabled is False

    def test_an_agent_is_found_in_its_account_and_by_id_alone(self, agent_repository):
        """Owner routes read an agent in its account; credentials and schedules find it by id alone."""
        agent = Agent(
            agent_name=AGENT_CREATE_REQUEST["agent_name"],
            agent_architecture=AGENT_CREATE_REQUEST["agent_architecture"],
            agent_provider=AGENT_CREATE_REQUEST["agent_provider"],
            agent_provider_api_key=AGENT_CREATE_REQUEST["agent_provider_api_key"],
            agent_persona=AGENT_CREATE_REQUEST["agent_persona"],
            **agent_fields(TEST_USER_EMAIL),
        )
        agent_repository.save(agent)

        account_id, _ = owner_ids(TEST_USER_EMAIL)
        other_account, _ = owner_ids(TEST_USER_EMAIL_2)

        assert agent_repository.find_in_account(account_id, agent.agent_id) == agent_repository.get(agent.agent_id)
        assert agent_repository.get(agent.agent_id).agent_name == agent.agent_name
        assert agent_repository.find_in_account(other_account, agent.agent_id) is None

    def test_list_owned(self, agent_repository):
        """An owner's agents in an account, and nobody else's."""
        # Create two agents for the same user
        agent1 = Agent(
            agent_name=AGENT_CREATE_REQUEST["agent_name"],
            agent_architecture=AGENT_CREATE_REQUEST["agent_architecture"],
            agent_provider=AGENT_CREATE_REQUEST["agent_provider"],
            agent_provider_api_key=AGENT_CREATE_REQUEST["agent_provider_api_key"],
            agent_persona=AGENT_CREATE_REQUEST["agent_persona"],
            **agent_fields(TEST_USER_EMAIL),
        )
        agent2 = Agent(
            agent_name=AGENT_CREATE_REQUEST_2["agent_name"],
            agent_architecture=AGENT_CREATE_REQUEST_2["agent_architecture"],
            agent_provider=AGENT_CREATE_REQUEST_2["agent_provider"],
            agent_provider_api_key=AGENT_CREATE_REQUEST_2["agent_provider_api_key"],
            agent_persona=AGENT_CREATE_REQUEST_2["agent_persona"],
            **agent_fields(TEST_USER_EMAIL),
        )
        agent_repository.save(agent1)
        agent_repository.save(agent2)

        agent_repository.save(Agent(
            agent_name="Someone else's", agent_architecture="krishna-mini", agent_provider="Bedrock",
            agent_persona="x", account_id=agent1.account_id, owner_id="someone-else", created_by="someone-else",
        ))

        agents = agent_repository.list_owned(*owner_ids(TEST_USER_EMAIL))

        assert len(agents) == 2
        agent_names = {a.agent_name for a in agents}
        assert AGENT_CREATE_REQUEST["agent_name"] in agent_names
        assert AGENT_CREATE_REQUEST_2["agent_name"] in agent_names

    def test_find_by_name(self, agent_repository):
        """Test that find_by_name() finds agent by name for a user."""
        agent = Agent(
            agent_name=AGENT_CREATE_REQUEST["agent_name"],
            agent_architecture=AGENT_CREATE_REQUEST["agent_architecture"],
            agent_provider=AGENT_CREATE_REQUEST["agent_provider"],
            agent_provider_api_key=AGENT_CREATE_REQUEST["agent_provider_api_key"],
            agent_persona=AGENT_CREATE_REQUEST["agent_persona"],
            **agent_fields(TEST_USER_EMAIL),
        )
        agent_repository.save(agent)

        found_agent = agent_repository.find_by_name(*owner_ids(TEST_USER_EMAIL), AGENT_CREATE_REQUEST["agent_name"])

        assert found_agent is not None
        assert found_agent.agent_name == AGENT_CREATE_REQUEST["agent_name"]

    def test_find_by_name_returns_none_for_different_user(self, agent_repository):
        """Test that find_by_name() returns None for a different user."""
        agent = Agent(
            agent_name=AGENT_CREATE_REQUEST["agent_name"],
            agent_architecture=AGENT_CREATE_REQUEST["agent_architecture"],
            agent_provider=AGENT_CREATE_REQUEST["agent_provider"],
            agent_provider_api_key=AGENT_CREATE_REQUEST["agent_provider_api_key"],
            agent_persona=AGENT_CREATE_REQUEST["agent_persona"],
            **agent_fields(TEST_USER_EMAIL),
        )
        agent_repository.save(agent)

        found_agent = agent_repository.find_by_name(*owner_ids(TEST_USER_EMAIL_2), AGENT_CREATE_REQUEST["agent_name"])

        assert found_agent is None

    def test_delete(self, agent_repository):
        """Test that delete() removes the agent."""
        agent = Agent(
            agent_name=AGENT_CREATE_REQUEST["agent_name"],
            agent_architecture=AGENT_CREATE_REQUEST["agent_architecture"],
            agent_provider=AGENT_CREATE_REQUEST["agent_provider"],
            agent_provider_api_key=AGENT_CREATE_REQUEST["agent_provider_api_key"],
            agent_persona=AGENT_CREATE_REQUEST["agent_persona"],
            **agent_fields(TEST_USER_EMAIL),
        )
        agent_repository.save(agent)

        result = agent_repository.delete(agent.account_id, agent.agent_id)

        assert result is True
        assert agent_repository.get(agent.agent_id) is None

    def test_save_updates_existing_agent(self, agent_repository):
        """Test that save() updates an existing agent."""
        agent = Agent(
            agent_name=AGENT_CREATE_REQUEST["agent_name"],
            agent_architecture=AGENT_CREATE_REQUEST["agent_architecture"],
            agent_provider=AGENT_CREATE_REQUEST["agent_provider"],
            agent_provider_api_key=AGENT_CREATE_REQUEST["agent_provider_api_key"],
            agent_persona=AGENT_CREATE_REQUEST["agent_persona"],
            **agent_fields(TEST_USER_EMAIL),
        )
        saved_agent = agent_repository.save(agent)
        original_created_at = saved_agent.created_at

        # Update the agent
        saved_agent.agent_persona = "Updated persona"
        updated_agent = agent_repository.save(saved_agent)

        assert updated_agent.agent_persona == "Updated persona"
        assert updated_agent.created_at == original_created_at
        assert updated_agent.updated_at is not None

    def test_list_agent2agent_enabled_returns_only_enabled_agents(self, agent_repository):
        """Test listing agents enabled for A2A discovery."""
        enabled_agent = Agent(
            agent_name=AGENT_CREATE_REQUEST["agent_name"],
            agent_architecture=AGENT_CREATE_REQUEST["agent_architecture"],
            agent_provider=AGENT_CREATE_REQUEST["agent_provider"],
            agent_persona=AGENT_CREATE_REQUEST["agent_persona"],
            **agent_fields(TEST_USER_EMAIL),
            is_agent2agent_enabled=True,
        )
        disabled_agent = Agent(
            agent_name=AGENT_CREATE_REQUEST_2["agent_name"],
            agent_architecture=AGENT_CREATE_REQUEST_2["agent_architecture"],
            agent_provider=AGENT_CREATE_REQUEST_2["agent_provider"],
            agent_persona=AGENT_CREATE_REQUEST_2["agent_persona"],
            **agent_fields(TEST_USER_EMAIL),
            is_agent2agent_enabled=False,
        )
        agent_repository.save(enabled_agent)
        agent_repository.save(disabled_agent)

        page = agent_repository.list_agent2agent_enabled()

        assert page.cursor is None
        assert [agent.agent_id for agent in page.items] == [enabled_agent.agent_id]

        found = agent_repository.find_agent2agent_enabled_by_id(enabled_agent.agent_id)
        assert found is not None
        assert found.agent_id == enabled_agent.agent_id
        assert agent_repository.find_agent2agent_enabled_by_id(disabled_agent.agent_id) is None
