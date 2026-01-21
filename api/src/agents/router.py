from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field, field_validator
from typing import Annotated, Any
import logging

import src.form_models as form_models
from src.agents.architectures import get_agent_architecture
from src.agents.models import Agent, CreateAgentRequest, AgentResponse
from src.agents.repository import AgentRepository
from src.agents.schemas import get_create_agent_form, get_update_agent_form, UPDATE_AGENT_FORM
from src.conversations.repository import ConversationRepository
from src.crypto import encrypt_secret_fields
from src.llm.events import SSEEvent, SSEEventType
from src.llm.models import models_service
from src.messages.models import Attachment, MAX_FILES, MAX_TOTAL_SIZE
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository

log = logging.getLogger(__name__)

# Security scheme for Swagger UI - tells Swagger these endpoints need auth
security = HTTPBearer()

router = APIRouter(
    prefix="/agents",
    tags=['agents'],
    dependencies=[Depends(security)]  # Apply to all routes in this router
)

class SendMessageRequest(BaseModel):
    """Request body for sending a message to an agent."""

    content: str
    attachments: list[dict[str, Any]] | None = None
    

    @field_validator("attachments")
    @classmethod
    def validate_attachments(cls, v: list[dict[str, Any]] | None) -> list[Attachment]:
        if v is None:
            return []
        if len(v) > MAX_FILES:
            raise ValueError(f"Maximum {MAX_FILES} files allowed")

        total_size = sum(att.get("size", 0) for att in v)
        if total_size > MAX_TOTAL_SIZE:
            raise ValueError(f"Total attachment size exceeds {MAX_TOTAL_SIZE // 1024}KB")

        # Validate and convert each attachment
        return [Attachment(**att) for att in v]


def get_agent_repository() -> AgentRepository:
    """Dependency for AgentRepository"""
    return AgentRepository()


@router.get("/supported-models", response_model=form_models.Form, response_model_exclude_none=True)
async def get_create_agent_schema(
    request: Request,
    providers_settings_repo: Annotated[ProviderSettingsRepository, Depends(get_provider_settings_repository)]) -> form_models.Form:
    """Get the form schema for creating an agent with dynamically fetched models."""
    # Fetch available models from Bedrock with display names
    user_email = request.state.user_email
    
    bedrock_models = models_service.get_bedrock_models()
    model_providers = ["Bedrock"]
    model_options = [
        {"value": m.model_name, "label": m.display_name}
        for m in bedrock_models
    ]
    
    
    provider_settings = providers_settings_repo.find_by_provider(user_email=user_email, provider_name="Anthropic")
    
    if provider_settings:
        anthropic_models = models_service.get_anthropic_models(provider_settings=provider_settings)
        model_providers.append("Anthropic")
        model_options.extend([
            {"value": m.model_name, "label": m.display_name}
            for m in anthropic_models
        ])
    
    return get_create_agent_form(model_providers, model_options)


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

    # Create new agent (API keys now stored in provider settings)
    agent = Agent(
        agent_name=create_request.agent_name,
        agent_architecture=create_request.agent_architecture,
        agent_provider=create_request.agent_provider,
        agent_model=create_request.agent_model,
        agent_persona=create_request.agent_persona,
        created_by=user_email,
    )

    saved_agent = repo.save(agent)
    log.info(f"Created new agent '{saved_agent.agent_name}' (id={saved_agent.agent_id}) for user {user_email}")

    return saved_agent.to_response()


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    request: Request,
    repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> list[AgentResponse]:
    """
    List all agents for the authenticated user.
    """
    user_email: str = request.state.user_email
    agents = repo.find_all_by_created_by(user_email)
    return [agent.to_response() for agent in agents]


@router.get("/update-schema/{agent_id}", response_model=form_models.Form, response_model_exclude_none=True)
async def get_update_agent_schema(agent_id: str) -> form_models.Form:
    """Get the form schema for updating an agent with dynamically fetched models."""
    # Fetch available models from Bedrock with display names
    bedrock_models = models_service.get_bedrock_models()
    model_options = [
        {"value": m.model_name, "label": m.display_name}
        for m in bedrock_models
    ]
    return get_update_agent_form(agent_id, model_options)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    request: Request,
    agent_id: str,
    repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> AgentResponse:
    """
    Get an agent by ID. Returns 404 if not found or not owned by user.
    """
    user_email: str = request.state.user_email
    agent = repo.find_agent_by_id(agent_id, user_email)

    if not agent:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Agent not found")

    return agent.to_response()


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    request: Request,
    agent_id: str,
    update_data: dict[str, Any],
    repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> AgentResponse:
    """
    Update an agent by ID. Only fields present in the request are updated.
    Password fields are automatically encrypted based on the form schema.

    This endpoint is idempotent - calling with same data returns same result.
    Returns 404 if agent not found or not owned by user.
    """
    user_email: str = request.state.user_email
    agent = repo.find_agent_by_id(agent_id, user_email)

    if not agent:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Agent not found")

    # Get valid field names from schema
    valid_fields = {field.name for field in UPDATE_AGENT_FORM.form_inputs}

    # Filter to only valid fields that are present in request
    filtered_data = {k: v for k, v in update_data.items() if k in valid_fields and v is not None}

    if not filtered_data:
        # No valid fields to update, return current agent (idempotent)
        return agent.to_response()

    # Encrypt secret fields based on form schema
    encrypted_data = encrypt_secret_fields(UPDATE_AGENT_FORM, filtered_data)

    # Apply updates to agent
    for field_name, value in encrypted_data.items():
        setattr(agent, field_name, value)

    saved_agent = repo.save(agent)
    log.info(f"Updated agent '{saved_agent.agent_name}' (id={saved_agent.agent_id}) for user {user_email}")

    return saved_agent.to_response()


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    request: Request,
    agent_id: str,
    repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> None:
    """
    Delete an agent by ID.

    This endpoint is idempotent - returns success even if agent doesn't exist.
    """
    user_email: str = request.state.user_email
    repo.delete_by_id(agent_id, user_email)
    log.info(f"Deleted agent {agent_id} for user {user_email}")


@router.post("/{agent_id}/{conversation_id}/send-message")
async def send_message(
    request: Request,
    agent_id: str,
    conversation_id: str,
    body: SendMessageRequest,
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
):
    """
    Sends message to the agent along with the conversation id for the context.
    This endpoint returns a streaming response using Server Side Events.
    The structure of the event is standard with the payload marshalled into json object.

    Events:
    - LIFECYCLE_NOTIFICATION: Status updates during processing
    - AGENT_RESPONSE_TO_USER: Streaming response chunks from the LLM
    - MESSAGE_SAVED: Confirmation that user/assistant message was saved
    - STREAM_COMPLETE: Stream has finished
    - ERROR: An error occurred
    """
    user_email: str = request.state.user_email
    conversation_repo = ConversationRepository()

    async def event_stream():
        try:
            # 1. Load and validate agent
            yield SSEEvent(
                event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                content="Loading agent information..."
            ).to_sse()

            agent = agent_repo.find_agent_by_id(agent_id, user_email)
            if not agent:
                yield SSEEvent(
                    event_type=SSEEventType.ERROR,
                    content="Agent not found"
                ).to_sse()
                return

            # 2. Validate conversation ownership
            yield SSEEvent(
                event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                content="Validating conversation..."
            ).to_sse()

            conversation = conversation_repo.find_by_id(conversation_id, user_email)
            if not conversation:
                yield SSEEvent(
                    event_type=SSEEventType.ERROR,
                    content="Conversation not found"
                ).to_sse()
                return

            if conversation.agent_id != agent_id:
                yield SSEEvent(
                    event_type=SSEEventType.ERROR,
                    content="Conversation does not belong to this agent"
                ).to_sse()
                return

            # 3. Get architecture and delegate message handling
            architecture = get_agent_architecture(agent.agent_architecture)

            async for event in architecture.handle_message(
                agent=agent,
                conversation=conversation,
                user_message=body.content,
                user_email=user_email,
                attachments=body.attachments or [],
            ):
                yield event.to_sse()

            # 4. Update conversation timestamp after successful handling
            conversation_repo.save(conversation)

        except Exception as e:
            log.error(f"Error in send_message stream: {e}", exc_info=True)
            yield SSEEvent(
                event_type=SSEEventType.ERROR,
                content=str(e)
            ).to_sse()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
