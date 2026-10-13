import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field, field_validator
from typing import Annotated, Any, cast
from dataclasses import dataclass
import logging

import src.form_models as form_models
from src.config import settings
from src.agents.image_generation.models import GenerateImageRequest, GenerateImageResponse
from src.agents.image_generation.service import (
    AgentImageGenerationError,
    AgentImageGenerationService,
    ImageGenerationConflictError,
    ImageGenerationNotFoundError,
    ImageGenerationNotSupportedError,
)
from src.accounts.owner import Owner
from src.agents.access import access_to, owner_of, require_agent, visible_agents
from src.agents.models import Agent, CreateAgentRequest, AgentResponse
from src.agents.repository import AgentRepository
from src.agents.service import AgentService, validate_provider_model
from src.agents.schemas import get_create_agent_form, get_update_agent_form, UPDATE_AGENT_FORM
from src.agents.turns import (
    ConversationTurn,
    ConversationTurnRepository,
    ConversationTurnResponse,
    live_transcript,
    start_turn,
)
from src.agents.turns import stop_turn as stop_conversation_turn
from src.agents.turns.transcript import TurnTranscript
from src.a2a.models import A2ATaskListResponse, A2ATaskResponse
from src.a2a.repository import A2ATaskRepository
from src.apikeys.repository import ApiKeyRepository
from src.common.sse import sse_response
from src.conversations.models import Conversation
from src.conversations.repository import ConversationRepository
from src.crypto import encrypt_secret_fields
from src.dream.repository import DreamRepository
from src.dream.service import DreamService
from src.form_options import FormOptionsContext, hydrate_form_options
from src.iam.actions import ResourceRef
from src.iam.dependencies import get_owner, get_principal
from src.iam.principal import Principal
from src.llm.events import SSEEvent, SSEEventType
from src.messages.models import Attachment, MAX_FILES, MAX_TOTAL_SIZE
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository
from src.skills.models import ActorKind
from src.exceptions import GENERIC_ERROR_MESSAGE
from src.vision.policy import ImageInputAvailability, image_input_availability
from src.vision.uploads import ImageUploadService

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
    #: Images uploaded to this conversation (`POST /conversations/{id}/images`) and sent with the message.
    image_ids: list[str] = Field(default_factory=list)

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


class Agent2AgentSharingRequest(BaseModel):
    """Request body for toggling Agent2Agent discovery."""

    enabled: bool


class Agent2AgentSharingResponse(BaseModel):
    """Agent2Agent sharing settings for an agent."""

    agent_id: str
    enabled: bool
    agent_card_url: str
    service_url: str
    has_active_api_key: bool


def get_agent_repository() -> AgentRepository:
    """Dependency for AgentRepository"""
    return AgentRepository()


def get_api_key_repository() -> ApiKeyRepository:
    """Dependency for ApiKeyRepository."""
    return ApiKeyRepository()


def get_a2a_task_repository() -> A2ATaskRepository:
    """Dependency for A2ATaskRepository."""
    return A2ATaskRepository()


def get_agent_image_generation_service() -> AgentImageGenerationService:
    """Dependency for AgentImageGenerationService."""
    return AgentImageGenerationService()


def _agent2agent_sharing_response(
    *,
    agent: Agent,
    api_key_repo: ApiKeyRepository,
) -> Agent2AgentSharingResponse:
    active_keys = [key for key in api_key_repo.find_all_by_agent(agent.agent_id) if key.is_active]
    base_url = settings.api_base_url.rstrip("/")
    return Agent2AgentSharingResponse(
        agent_id=agent.agent_id,
        enabled=agent.is_agent2agent_enabled,
        agent_card_url=f"{base_url}/a2a/agents/{agent.agent_id}/card",
        service_url=f"{base_url}/a2a/agents/{agent.agent_id}",
        has_active_api_key=bool(active_keys),
    )


@router.get("/supported-models", response_model=form_models.Form, response_model_exclude_none=True)
async def get_create_agent_schema(
    owner: Annotated[Owner, Depends(get_owner)],
    providers_settings_repo: Annotated[ProviderSettingsRepository, Depends(get_provider_settings_repository)]) -> form_models.Form:
    """Get the form schema for creating an agent with dynamically fetched models."""
    return hydrate_form_options(
        get_create_agent_form(),
        FormOptionsContext(
            owner=owner,
            provider_settings_repository=providers_settings_repo,
        ),
    )


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
    create_request: CreateAgentRequest,
    repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    principal: Annotated[Principal, Depends(get_principal)],
    owner: Annotated[Owner, Depends(get_owner)],
) -> AgentResponse:
    """
    Create a new agent for the authenticated user.

    This endpoint is idempotent - if an agent with the same name already exists
    for the user, it returns the existing agent instead of creating a duplicate.

    The new agent belongs to the caller, in the account the request acts in.
    """
    principal.require("agents:Create", ResourceRef("agent"))

    # Idempotency check: look for existing agent with same name for this user
    existing_agent = repo.find_by_name(owner.account_id, owner.user_id, create_request.agent_name)
    if existing_agent:
        log.info(f"Agent '{create_request.agent_name}' already exists for {owner.user_id}, returning existing")
        return existing_agent.to_response()

    _require_provider_model(owner, create_request.agent_provider, create_request.agent_model)
    return AgentService(repo).create(create_request, owner).to_response()


def _require_provider_model(owner: Owner, provider: str, model: str | None) -> None:
    try:
        validate_provider_model(owner, provider, model or None)
    except ValueError:
        offered = f"{model} on {provider}" if model else provider
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{offered} isn't available. Choose a provider your account has set up in Settings, and one of its models.",
        )


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> list[AgentResponse]:
    """
    The account's agents the caller can see: their own, those shared with them, and, for admins,
    everyone else's as metadata. Each says how the caller reaches it (`access`).
    """
    return [agent.to_response(access) for agent, access in visible_agents(principal, repo)]


@router.get("/update-schema/{agent_id}", response_model=form_models.Form, response_model_exclude_none=True)
async def get_update_agent_schema(
    agent_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    providers_settings_repo: Annotated[ProviderSettingsRepository, Depends(get_provider_settings_repository)]
) -> form_models.Form:
    """Get the form schema for updating an agent: the models offered are its owner's."""
    agent = require_agent(principal, agent_id, "agents:Update")
    owner = owner_of(agent)
    return hydrate_form_options(
        get_update_agent_form(agent_id),
        FormOptionsContext(
            owner=owner,
            provider_settings_repository=providers_settings_repo,
        ),
    )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> AgentResponse:
    """
    An agent the caller can see: in full with `agents:Get`, as metadata (no persona) with only
    `agents:Describe`. 404 if they can't see it at all.
    """
    agent = require_agent(principal, agent_id, "agents:Describe", repo)
    access = access_to(principal, agent)
    return agent.to_response(access or "admin")


@router.get("/{agent_id}/image-input", response_model=ImageInputAvailability)
async def get_image_input(
    agent_id: str,
    repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> ImageInputAvailability:
    """Whether the caller may attach images when chatting with this agent, and the limits to check them against."""
    agent = require_agent(principal, agent_id, "agents:Chat", repo)
    return await asyncio.to_thread(image_input_availability, agent)


@router.get("/{agent_id}/a2a-sharing", response_model=Agent2AgentSharingResponse)
async def get_agent2agent_sharing(
    request: Request,
    agent_id: str,
    repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    api_key_repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> Agent2AgentSharingResponse:
    """Get Agent2Agent discovery sharing settings for an agent."""
    agent = require_agent(principal, agent_id, "agents:Get", repo)

    return _agent2agent_sharing_response(agent=agent, api_key_repo=api_key_repo)


@router.put("/{agent_id}/a2a-sharing", response_model=Agent2AgentSharingResponse)
async def update_agent2agent_sharing(
    request: Request,
    agent_id: str,
    body: Agent2AgentSharingRequest,
    repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    api_key_repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> Agent2AgentSharingResponse:
    """Toggle Agent2Agent discovery sharing for an agent."""
    agent = require_agent(principal, agent_id, "agents:Update", repo)

    active_keys = [key for key in api_key_repo.find_all_by_agent(agent.agent_id) if key.is_active]
    if body.enabled and not active_keys:
        raise HTTPException(
            status_code=400,
            detail="Create an active API key before enabling Agent2Agent discovery",
        )

    agent.is_agent2agent_enabled = body.enabled
    saved_agent = repo.save(agent)
    return _agent2agent_sharing_response(agent=saved_agent, api_key_repo=api_key_repo)


@router.get("/{agent_id}/a2a-tasks", response_model=A2ATaskListResponse)
async def list_agent2agent_tasks(
    request: Request,
    agent_id: str,
    repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    task_repo: Annotated[A2ATaskRepository, Depends(get_a2a_task_repository)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> A2ATaskListResponse:
    """List Agent2Agent tasks for an agent the caller may open."""
    require_agent(principal, agent_id, "agents:Get", repo)

    return A2ATaskListResponse(items=task_repo.find_by_agent(agent_id=agent_id))


@router.get("/{agent_id}/a2a-tasks/{task_id}", response_model=A2ATaskResponse)
async def get_agent2agent_task(
    request: Request,
    agent_id: str,
    task_id: str,
    repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    task_repo: Annotated[A2ATaskRepository, Depends(get_a2a_task_repository)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> A2ATaskResponse:
    """Get one Agent2Agent task for an agent the caller may open."""
    require_agent(principal, agent_id, "agents:Get", repo)

    task = task_repo.find_by_id(agent_id=agent_id, task_id=task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return A2ATaskResponse(task=task)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    update_data: dict[str, Any],
    repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> AgentResponse:
    """
    Update an agent by ID. Only fields present in the request are updated.
    Password fields are automatically encrypted based on the form schema.

    This endpoint is idempotent - calling with same data returns same result.
    Needs `agents:Update`. Models and dream settings are the agent's account's, whoever edits the agent.
    """
    agent = require_agent(principal, agent_id, "agents:Update", repo)
    owner = owner_of(agent)

    # Get valid field names from schema
    valid_fields = {field.name for field in UPDATE_AGENT_FORM.form_inputs}

    # Filter to only valid fields that are present in request
    filtered_data = {k: v for k, v in update_data.items() if k in valid_fields and v is not None}

    if not filtered_data:
        # No valid fields to update, return current agent (idempotent)
        return agent.to_response()

    # Only a changed pair is checked: an older agent keeps working while its provider stops listing its model.
    provider = filtered_data.get("agent_provider", agent.agent_provider)
    model = filtered_data.get("agent_model", agent.agent_model)
    if (provider, model) != (agent.agent_provider, agent.agent_model):
        _require_provider_model(owner, provider, model)

    # Encrypt secret fields based on form schema
    encrypted_data = encrypt_secret_fields(UPDATE_AGENT_FORM, filtered_data)

    # Apply updates to agent
    for field_name, value in encrypted_data.items():
        setattr(agent, field_name, value)

    saved_agent = repo.save(agent)
    dream_service = DreamService()
    dream_settings = DreamRepository().find_settings(saved_agent.account_id)
    if saved_agent.agent_architecture == "krishna-memgpt" and dream_settings:
        dream_service.ensure_schedule(saved_agent.agent_id, owner.email, owner, dream_settings)
    elif saved_agent.agent_architecture != "krishna-memgpt":
        dream_service.delete_schedule(saved_agent.agent_id, owner.email, owner)
    log.info(f"Updated agent '{saved_agent.agent_name}' (id={saved_agent.agent_id}) by {principal.user_id}")

    return saved_agent.to_response()


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> None:
    """Delete an agent, its shares, keys and media. Needs `agents:Delete` (the owner, or an admin)."""
    agent = require_agent(principal, agent_id, "agents:Delete", repo)
    AgentService(repo).delete(agent, owner_of(agent).email)


@dataclass(frozen=True)
class ChatTarget:
    """The (agent, conversation) pair a chat endpoint acts on, and who is chatting."""

    agent: Agent
    conversation: Conversation
    caller: Owner


def resolve_chat_target(
    agent_id: str,
    conversation_id: str,
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    principal: Annotated[Principal, Depends(get_principal)],
    caller: Annotated[Owner, Depends(get_owner)],
) -> ChatTarget:
    """Load the agent the caller may chat with, and their own conversation with it; 404 on any mismatch."""
    agent = require_agent(principal, agent_id, "agents:Chat", agent_repo)

    # A conversation belongs to whoever started it, even on someone else's agent
    conversation = ConversationRepository().find_by_id(conversation_id, caller.member_pk)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Conversation does not belong to this agent")

    return ChatTarget(agent=agent, conversation=conversation, caller=caller)


@dataclass(frozen=True)
class ChatTurnTarget:
    """A chat target plus one of its turns."""

    agent: Agent
    conversation: Conversation
    turn: ConversationTurn


def resolve_chat_turn(
    turn_id: str,
    target: Annotated[ChatTarget, Depends(resolve_chat_target)],
) -> ChatTurnTarget:
    """Load a turn that genuinely belongs to this agent and conversation."""
    turn = ConversationTurnRepository().find_by_id(turn_id)
    if (
        not turn
        or turn.conversation_id != target.conversation.conversation_id
        or turn.agent_id != target.agent.agent_id
    ):
        raise HTTPException(status_code=404, detail="Turn not found")

    return ChatTurnTarget(agent=target.agent, conversation=target.conversation, turn=turn)


async def _stream_transcript(transcript: TurnTranscript, *, after_sequence: int):
    async for sequence, event in transcript.follow(after_sequence=after_sequence):
        yield f"id: {sequence}\n{event.to_sse()}"


@router.post("/{agent_id}/{conversation_id}/send-message")
async def send_message(
    request: Request,
    body: SendMessageRequest,
    target: Annotated[ChatTarget, Depends(resolve_chat_target)],
):
    """
    Sends message to the agent along with the conversation id for the context.

    The turn runs to completion server-side even if this connection closes —
    see api/docs/LLD-async-chat-turns.md. The response carries an `X-Turn-Id`
    header; a client that reconnects mid-turn tails
    `GET /{agent_id}/{conversation_id}/turns/{turn_id}/events?after_sequence=N`
    instead of resending the message. A second message on a conversation that
    already has a turn running is rejected with 409, carrying that turn's id.

    This endpoint returns a streaming response using Server Side Events.
    The structure of the event is standard with the payload marshalled into json object.

    Events:
    - LIFECYCLE_NOTIFICATION: Status updates during processing
    - AGENT_RESPONSE_TO_USER: Streaming response chunks from the LLM
    - USER_MESSAGE_SAVED: Confirmation that the user message was saved
    - ASSISTANT_MESSAGE_SAVED: Confirmation that the assistant message was saved
    - STREAM_COMPLETE: Stream has finished successfully
    - ERROR: An error occurred
    """
    active_turn = ConversationTurnRepository().find_active(target.conversation.conversation_id)
    if active_turn:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "This conversation already has a response in progress.",
                "turn_id": active_turn.turn_id,
            },
        )

    images = await asyncio.to_thread(
        ImageUploadService().attach,
        agent=target.agent,
        conversation_id=target.conversation.conversation_id,
        actor_id=target.caller.user_id,
        image_ids=body.image_ids,
    )
    running = start_turn(
        agent=target.agent,
        conversation=target.conversation,
        user_message=body.content,
        attachments=cast(list[Attachment], body.attachments or []),
        images=images,
        # The agent runs as its owner (their provider keys, skills and connections); the caller is
        # who speaks, and whose memory it keeps
        owner_email=owner_of(target.agent).email,
        actor_email=target.caller.email,
        actor_id=target.caller.email,
        actor_kind=ActorKind.OWNER if target.agent.owner_id == target.caller.user_id else ActorKind.MEMBER,
    )
    response = sse_response(_stream_transcript(running.transcript, after_sequence=0))
    response.headers["X-Turn-Id"] = running.turn.turn_id
    return response


@router.get("/{agent_id}/{conversation_id}/turns/active")
async def get_active_turn(
    target: Annotated[ChatTarget, Depends(resolve_chat_target)],
) -> ConversationTurnResponse | None:
    """Report the running turn for this conversation, if any, so the SPA can reattach."""
    turn = ConversationTurnRepository().find_active(target.conversation.conversation_id)
    if not turn or turn.agent_id != target.agent.agent_id:
        return None
    return turn.to_response()


@router.get("/{agent_id}/{conversation_id}/turns/{turn_id}/events")
async def stream_turn_events(
    target: Annotated[ChatTurnTarget, Depends(resolve_chat_turn)],
    after_sequence: int = 0,
):
    """
    Tail a turn's transcript: replay everything after `after_sequence`, then follow live.

    Powers reattaching to an in-flight response after navigation or a page
    refresh. Returns 410 once the turn has finished and its transcript's grace
    window has passed — by then the assistant message is already persisted, so
    the client should simply refetch messages.
    """
    transcript = live_transcript(target.turn.turn_id)
    if transcript is None:
        raise HTTPException(status_code=410, detail="This response is no longer available.")

    return sse_response(_stream_transcript(transcript, after_sequence=after_sequence))


@router.post("/{agent_id}/{conversation_id}/turns/{turn_id}/stop", status_code=204)
async def stop_turn(
    target: Annotated[ChatTurnTarget, Depends(resolve_chat_turn)],
) -> None:
    """Stop an in-progress chat turn."""
    stop_conversation_turn(target.turn)

@router.post("/{agent_id}/{conversation_id}/generate-image", response_model=GenerateImageResponse)
async def generate_image(
    body: GenerateImageRequest,
    target: Annotated[ChatTarget, Depends(resolve_chat_target)],
    service: Annotated[AgentImageGenerationService, Depends(get_agent_image_generation_service)],
) -> GenerateImageResponse:
    """Explicitly generate an image with an agent and save it to chat history."""
    try:
        return await service.generate_for_dashboard(
            agent=target.agent,
            conversation=target.conversation,
            actor_email=target.caller.email,
            request=body,
        )
    except ImageGenerationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ImageGenerationConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ImageGenerationNotSupportedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except AgentImageGenerationError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{agent_id}/{conversation_id}/generate-image-stream")
async def generate_image_stream(
    body: GenerateImageRequest,
    target: Annotated[ChatTarget, Depends(resolve_chat_target)],
    service: Annotated[AgentImageGenerationService, Depends(get_agent_image_generation_service)],
):
    """Explicitly generate an image with an agent and stream preview/final events."""

    async def event_stream():
        try:
            async for event in service.stream_for_dashboard(
                agent=target.agent,
                conversation=target.conversation,
                actor_email=target.caller.email,
                request=body,
            ):
                yield event.to_sse()
        except ImageGenerationNotFoundError as e:
            yield SSEEvent(event_type=SSEEventType.ERROR, content=str(e)).to_sse()
        except ImageGenerationConflictError as e:
            yield SSEEvent(event_type=SSEEventType.ERROR, content=str(e)).to_sse()
        except ImageGenerationNotSupportedError as e:
            yield SSEEvent(event_type=SSEEventType.ERROR, content=str(e)).to_sse()
        except Exception as e:
            log.error("Error in generate_image_stream: %s", e, exc_info=True)
            yield SSEEvent(event_type=SSEEventType.ERROR, content=GENERIC_ERROR_MESSAGE).to_sse()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
