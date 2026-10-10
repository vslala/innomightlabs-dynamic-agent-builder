"""Creating and deleting agents. Shared by the agents routes, the marketplace import and blueprints."""

import logging
from typing import Optional

from src.accounts.owner import Owner
from src.agents.image_generation.storage import ConversationMediaStorage
from src.agents.models import Agent, CreateAgentRequest
from src.agents.repository import AgentRepository
from src.agents.schemas import get_create_agent_form
from src.apikeys.repository import ApiKeyRepository
from src.dream.repository import DreamRepository
from src.dream.service import DreamService
from src.form_options import FormOptionsContext, validate_form_options
from src.iam.shares import ShareService
from src.public_api.keys import SecretKeyRepository

log = logging.getLogger(__name__)


class AgentService:
    def __init__(self, repository: Optional[AgentRepository] = None) -> None:
        self.repository = repository or AgentRepository()

    def create(self, request: CreateAgentRequest, owner: Owner, *, agent_id: Optional[str] = None) -> Agent:
        """Save a new agent. A `krishna-memgpt` agent joins the owner's dream schedule if they have one.

        `agent_id` lets a caller choose the id ahead, so it can undo the create even if it stops before this returns
        (a blueprint apply records its undo first)."""
        agent = Agent(
            agent_name=request.agent_name,
            agent_architecture=request.agent_architecture,
            agent_provider=request.agent_provider,
            agent_model=request.agent_model,
            agent_persona=request.agent_persona,
            agent_description=request.agent_description,
            agent_ollama_thinking=request.agent_ollama_thinking,
            account_id=owner.account_id,
            owner_id=owner.user_id,
            created_by=owner.user_id,
        )
        if agent_id:
            agent.agent_id = agent_id
        if request.session_timeout_minutes is not None:
            agent.session_timeout_minutes = request.session_timeout_minutes

        saved_agent = self.repository.save(agent)
        if saved_agent.agent_architecture == "krishna-memgpt":
            dream_settings = DreamRepository().find_settings(owner.account_id)
            if dream_settings:
                DreamService().ensure_schedule(saved_agent.agent_id, owner.email, owner, dream_settings)
        log.info(f"Created agent '{saved_agent.agent_name}' (id={saved_agent.agent_id}) for {owner.user_id}")
        return saved_agent

    def delete(self, agent: Agent, owner_email: str) -> None:
        """Delete an agent with its dream schedule, shares, keys and media. The caller has authorized it.
        `owner_email` is the agent owner's, which dream schedules are still keyed by."""
        agent_id = agent.agent_id
        owner = Owner(account_id=agent.account_id, user_id=agent.owner_id, email=owner_email)
        DreamService().delete_schedule(agent_id, owner_email, owner)
        self.repository.delete(agent.account_id, agent_id)
        ShareService().forget_resource(agent.account_id, "agent", agent_id)
        SecretKeyRepository().delete_all_by_agent(agent_id)
        ApiKeyRepository().delete_all_by_agent(agent_id)
        try:
            ConversationMediaStorage().delete_agent_prefix(agent_id)
        except Exception:
            log.warning("Failed to delete media for agent %s", agent_id, exc_info=True)
        log.info(f"Deleted agent {agent_id} from account {agent.account_id}")


def validate_provider_model(owner: Owner, provider: str, model: Optional[str]) -> None:
    """Raises ValueError when the provider or model isn't one the create-agent form offers in the owner's account."""
    values = {"agent_provider": provider}
    if model:
        values["agent_model"] = model
    validate_form_options(
        get_create_agent_form().form_inputs,
        values,
        FormOptionsContext(owner=owner),
    )
