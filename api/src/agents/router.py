from fastapi import APIRouter, Depends, Request, status
from fastapi.security import HTTPBearer
from typing import Annotated
import logging

import src.form_models as form_models
from src.agents.models import Agent, CreateAgentRequest, AgentResponse
from src.agents.repository import AgentRepository
from src.agents.schemas import CREATE_AGENT_FORM
from src.crypto import encrypt_secret_fields

log = logging.getLogger(__name__)

# Security scheme for Swagger UI - tells Swagger these endpoints need auth
security = HTTPBearer()

router = APIRouter(
    prefix="/agents",
    tags=['agents'],
    dependencies=[Depends(security)]  # Apply to all routes in this router
)


def get_agent_repository() -> AgentRepository:
    """Dependency for AgentRepository"""
    return AgentRepository()


@router.get("/supported-models", response_model=form_models.Form, response_model_exclude_none=True)
async def get_create_agent_schema() -> form_models.Form:
    """Get the form schema for creating an agent"""
    return CREATE_AGENT_FORM


@router.post(
    "",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Agent already exists (idempotent)", "model": AgentResponse},
        201: {"description": "Agent created successfully", "model": AgentResponse},
    }
)
async def create_agent(
    request: Request,
    create_request: CreateAgentRequest,
    repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> AgentResponse:
    """
    Create a new agent for the authenticated user.

    This endpoint is idempotent - if an agent with the same name already exists
    for the user, it returns the existing agent instead of creating a duplicate.

    Args:
        request: FastAPI request (contains user_email from auth middleware)
        create_request: Agent creation request data
        repo: Agent repository dependency

    Returns:
        AgentResponse: The created or existing agent (without sensitive fields)
    """
    # Get user email from auth middleware
    user_email: str = request.state.user_email

    # Idempotency check: look for existing agent with same name for this user
    existing_agent = repo.find_by_name(create_request.agent_name, user_email)
    if existing_agent:
        log.info(f"Agent '{create_request.agent_name}' already exists for user {user_email}, returning existing")
        return existing_agent.to_response()

    # Encrypt secret fields based on form schema
    encrypted_data = encrypt_secret_fields(
        CREATE_AGENT_FORM,
        create_request.model_dump()
    )

    # Create new agent with encrypted secrets
    agent = Agent(
        agent_name=encrypted_data["agent_name"],
        agent_provider=encrypted_data["agent_provider"],
        agent_provider_api_key=encrypted_data["agent_provider_api_key"],
        agent_persona=encrypted_data["agent_persona"],
        created_by=user_email,
    )

    saved_agent = repo.save(agent)
    log.info(f"Created new agent '{saved_agent.agent_name}' (id={saved_agent.agent_id}) for user {user_email}")

    return saved_agent.to_response()
