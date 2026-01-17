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
            created_by=TEST_USER_EMAIL,
        )

        saved_agent = agent_repository.save(agent)

        assert saved_agent.agent_id == agent.agent_id
        assert saved_agent.agent_name == AGENT_CREATE_REQUEST["agent_name"]
        assert saved_agent.created_by == TEST_USER_EMAIL

    def test_find_agent_by_id(self, agent_repository):
        """Test that find_agent_by_id() retrieves the correct agent."""
        agent = Agent(
            agent_name=AGENT_CREATE_REQUEST["agent_name"],
            agent_architecture=AGENT_CREATE_REQUEST["agent_architecture"],
            agent_provider=AGENT_CREATE_REQUEST["agent_provider"],
            agent_provider_api_key=AGENT_CREATE_REQUEST["agent_provider_api_key"],
            agent_persona=AGENT_CREATE_REQUEST["agent_persona"],
            created_by=TEST_USER_EMAIL,
        )
        agent_repository.save(agent)

        found_agent = agent_repository.find_agent_by_id(agent.agent_id, TEST_USER_EMAIL)

        assert found_agent is not None
        assert found_agent.agent_id == agent.agent_id
        assert found_agent.agent_name == agent.agent_name

    def test_find_all_by_created_by(self, agent_repository):
        """Test that find_all_by_created_by() retrieves all agents for a user."""
        # Create two agents for the same user
        agent1 = Agent(
            agent_name=AGENT_CREATE_REQUEST["agent_name"],
            agent_architecture=AGENT_CREATE_REQUEST["agent_architecture"],
            agent_provider=AGENT_CREATE_REQUEST["agent_provider"],
            agent_provider_api_key=AGENT_CREATE_REQUEST["agent_provider_api_key"],
            agent_persona=AGENT_CREATE_REQUEST["agent_persona"],
            created_by=TEST_USER_EMAIL,
        )
        agent2 = Agent(
            agent_name=AGENT_CREATE_REQUEST_2["agent_name"],
            agent_architecture=AGENT_CREATE_REQUEST_2["agent_architecture"],
            agent_provider=AGENT_CREATE_REQUEST_2["agent_provider"],
            agent_provider_api_key=AGENT_CREATE_REQUEST_2["agent_provider_api_key"],
            agent_persona=AGENT_CREATE_REQUEST_2["agent_persona"],
            created_by=TEST_USER_EMAIL,
        )
        agent_repository.save(agent1)
        agent_repository.save(agent2)

        agents = agent_repository.find_all_by_created_by(TEST_USER_EMAIL)

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
            created_by=TEST_USER_EMAIL,
        )
        agent_repository.save(agent)

        found_agent = agent_repository.find_by_name(
            AGENT_CREATE_REQUEST["agent_name"], TEST_USER_EMAIL
        )

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
            created_by=TEST_USER_EMAIL,
        )
        agent_repository.save(agent)

        found_agent = agent_repository.find_by_name(
            AGENT_CREATE_REQUEST["agent_name"], TEST_USER_EMAIL_2
        )

        assert found_agent is None

    def test_delete_by_id(self, agent_repository):
        """Test that delete_by_id() removes the agent."""
        agent = Agent(
            agent_name=AGENT_CREATE_REQUEST["agent_name"],
            agent_architecture=AGENT_CREATE_REQUEST["agent_architecture"],
            agent_provider=AGENT_CREATE_REQUEST["agent_provider"],
            agent_provider_api_key=AGENT_CREATE_REQUEST["agent_provider_api_key"],
            agent_persona=AGENT_CREATE_REQUEST["agent_persona"],
            created_by=TEST_USER_EMAIL,
        )
        agent_repository.save(agent)

        result = agent_repository.delete_by_id(agent.agent_id, TEST_USER_EMAIL)

        assert result is True
        assert agent_repository.find_agent_by_id(agent.agent_id, TEST_USER_EMAIL) is None

    def test_save_updates_existing_agent(self, agent_repository):
        """Test that save() updates an existing agent."""
        agent = Agent(
            agent_name=AGENT_CREATE_REQUEST["agent_name"],
            agent_architecture=AGENT_CREATE_REQUEST["agent_architecture"],
            agent_provider=AGENT_CREATE_REQUEST["agent_provider"],
            agent_provider_api_key=AGENT_CREATE_REQUEST["agent_provider_api_key"],
            agent_persona=AGENT_CREATE_REQUEST["agent_persona"],
            created_by=TEST_USER_EMAIL,
        )
        saved_agent = agent_repository.save(agent)
        original_created_at = saved_agent.created_at

        # Update the agent
        saved_agent.agent_persona = "Updated persona"
        updated_agent = agent_repository.save(saved_agent)

        assert updated_agent.agent_persona == "Updated persona"
        assert updated_agent.created_at == original_created_at
        assert updated_agent.updated_at is not None
