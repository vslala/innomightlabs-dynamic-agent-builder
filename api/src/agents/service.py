"""Creating and deleting agents. Shared by the agents routes, the marketplace import and blueprints."""

import logging
from typing import Optional

from src.agents.image_generation.storage import ConversationMediaStorage
from src.agents.models import Agent, CreateAgentRequest
from src.agents.repository import AgentRepository
from src.agents.schemas import get_create_agent_form
from src.apikeys.repository import ApiKeyRepository
from src.dream.repository import DreamRepository
from src.dream.service import DreamService
from src.form_options import FormOptionsContext, validate_form_options
from src.public_api.keys import SecretKeyRepository

log = logging.getLogger(__name__)


class AgentService:
    def __init__(self, repository: Optional[AgentRepository] = None) -> None:
        self.repository = repository or AgentRepository()

    def create(self, request: CreateAgentRequest, user_email: str) -> Agent:
        """Save a new agent. A `krishna-memgpt` agent joins the owner's dream schedule if they have one."""
        agent = Agent(
            agent_name=request.agent_name,
            agent_architecture=request.agent_architecture,
            agent_provider=request.agent_provider,
            agent_model=request.agent_model,
            agent_persona=request.agent_persona,
            agent_description=request.agent_description,
            agent_ollama_thinking=request.agent_ollama_thinking,
            created_by=user_email,
        )
        if request.session_timeout_minutes is not None:
            agent.session_timeout_minutes = request.session_timeout_minutes

        saved_agent = self.repository.save(agent)
        if saved_agent.agent_architecture == "krishna-memgpt":
            dream_settings = DreamRepository().find_settings(user_email)
            if dream_settings:
                DreamService().ensure_schedule(saved_agent.agent_id, user_email, user_email, dream_settings)
        log.info(f"Created new agent '{saved_agent.agent_name}' (id={saved_agent.agent_id}) for user {user_email}")
        return saved_agent

    def delete(self, agent_id: str, user_email: str) -> None:
        """Delete an agent with its dream schedule, keys and media. The caller has checked the owner."""
        DreamService().delete_schedule(agent_id, user_email, user_email)
        self.repository.delete_by_id(agent_id, user_email)
        SecretKeyRepository().delete_all_by_agent(agent_id)
        ApiKeyRepository().delete_all_by_agent(agent_id)
        try:
            ConversationMediaStorage().delete_agent_prefix(agent_id)
        except Exception:
            log.warning("Failed to delete media for agent %s", agent_id, exc_info=True)
        log.info(f"Deleted agent {agent_id} for user {user_email}")


def validate_provider_model(user_email: str, provider: str, model: Optional[str]) -> None:
    """Raises ValueError when the provider or model isn't one the create-agent form offers this user."""
    values = {"agent_provider": provider}
    if model:
        values["agent_model"] = model
    validate_form_options(
        get_create_agent_form().form_inputs,
        values,
        FormOptionsContext(user_email=user_email),
    )
