"""
Building with Ada.

Endpoints:
    GET  /builder/session-form                          Provider and model to build with (a SchemaForm)
    POST /builder/sessions                              Start a building conversation, greeted by Ada
    GET  /builder/sessions                              The person's building conversations
    POST /builder/{conversation_id}/send-message        A turn with Ada (SSE, like an agent's send-message)
    GET  /builder/{conversation_id}/turns/active        The running turn, to reattach
    GET  /builder/{conversation_id}/turns/{id}/events   Tail a turn's transcript
    POST /builder/{conversation_id}/turns/{id}/stop     Stop a turn

The chat routes mirror an agent's, so the dashboard chat works for Ada unchanged.
"""

import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel

import src.form_models as form_models
from src.agents.schemas import get_create_agent_form
from src.agents.service import validate_provider_model
from src.agents.turns import ConversationTurn, ConversationTurnRepository, ConversationTurnResponse
from src.agents.turns import live_transcript, start_turn, stop_turn
from src.agents.turns.transcript import TurnTranscript
from src.builder.ada import ADA_AGENT_ID, GREETING, ada_agent, ada_architecture
from src.builder.connections import start_connection
from src.builder.models import BuilderSession, BuilderSessionResponse, CreateBuilderSessionRequest
from src.builder.repository import BuilderSessionRepository
from src.common.sse import sse_response
from src.connectors.mcp.service import get_mcp_connector_service
from src.conversations.models import Conversation
from src.conversations.repository import ConversationRepository
from src.form_options import FormOptionsContext, hydrate_form_options
from src.messages.models import Message
from src.messages.repositories import get_message_repository
from src.settings.repository import get_provider_settings_repository
from src.skills.models import ActorKind

log = logging.getLogger(__name__)

router = APIRouter(prefix="/builder", tags=["builder"], dependencies=[Depends(HTTPBearer())])

#: The create-agent form's own provider and model fields, so the choices are the same everywhere.
SESSION_FORM_FIELDS = ("agent_provider", "agent_model")


class BuilderMessageRequest(BaseModel):
    content: str


class ConnectRequest(BaseModel):
    provider: str


class ConnectResponse(BaseModel):
    #: Where to sign in, in a popup. None when the account is already connected.
    authorize_url: str | None = None


@dataclass(frozen=True)
class BuildTarget:
    session: BuilderSession
    conversation: Conversation


def resolve_build(request: Request, conversation_id: str) -> BuildTarget:
    user_email: str = request.state.user_email
    session = BuilderSessionRepository().find(user_email, conversation_id)
    conversation = ConversationRepository().find_by_id(conversation_id, user_email)
    if session is None or conversation is None:
        raise HTTPException(status_code=404, detail="Building session not found")
    return BuildTarget(session=session, conversation=conversation)


def resolve_build_turn(turn_id: str, target: Annotated[BuildTarget, Depends(resolve_build)]) -> ConversationTurn:
    turn = ConversationTurnRepository().find_by_id(turn_id)
    if not turn or turn.conversation_id != target.conversation.conversation_id:
        raise HTTPException(status_code=404, detail="Turn not found")
    return turn


async def _stream(transcript: TurnTranscript, *, after_sequence: int):
    async for sequence, event in transcript.follow(after_sequence=after_sequence):
        yield f"id: {sequence}\n{event.to_sse()}"


@router.get("/session-form", response_model=form_models.Form, response_model_exclude_none=True)
async def session_form(request: Request) -> form_models.Form:
    """The person's own providers and models, filled in the same way as the create-agent form."""
    inputs = [field for field in get_create_agent_form().form_inputs if field.name in SESSION_FORM_FIELDS]
    form = form_models.Form(form_name="Build with Ada", submit_path="/builder/sessions", form_inputs=inputs)
    return hydrate_form_options(form, FormOptionsContext(user_email=request.state.user_email))


@router.post("/sessions", response_model=BuilderSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(request: Request, body: CreateBuilderSessionRequest) -> BuilderSessionResponse:
    user_email: str = request.state.user_email
    model = body.agent_model or None
    try:
        validate_provider_model(user_email, body.agent_provider, model)
    except ValueError:
        raise HTTPException(status_code=400, detail="Choose a provider and model you've set up.")
    if not get_provider_settings_repository().find_by_provider(user_email, body.agent_provider):
        raise HTTPException(
            status_code=400,
            detail=f"Set up {body.agent_provider} in Settings > Provider Configuration first.",
        )

    conversation = ConversationRepository().save(
        Conversation(title="Building with Ada", agent_id=ADA_AGENT_ID, created_by=user_email)
    )
    session = BuilderSessionRepository().save(BuilderSession(
        conversation_id=conversation.conversation_id,
        user_email=user_email,
        provider=body.agent_provider,
        model=model,
    ))
    get_message_repository().save(Message(
        conversation_id=conversation.conversation_id,
        created_by=user_email,
        role="assistant",
        content=GREETING,
    ))
    return _response(session)


@router.get("/sessions", response_model=list[BuilderSessionResponse])
async def list_sessions(request: Request) -> list[BuilderSessionResponse]:
    return [_response(session) for session in BuilderSessionRepository().list_by_user(request.state.user_email)]


@router.post("/{conversation_id}/send-message")
async def send_message(
    request: Request,
    body: BuilderMessageRequest,
    target: Annotated[BuildTarget, Depends(resolve_build)],
):
    user_email: str = request.state.user_email
    active = ConversationTurnRepository().find_active(target.conversation.conversation_id)
    if active:
        raise HTTPException(
            status_code=409,
            detail={"message": "Ada is still working on your last message.", "turn_id": active.turn_id},
        )
    running = start_turn(
        agent=ada_agent(target.session),
        conversation=target.conversation,
        user_message=body.content,
        attachments=None,
        owner_email=user_email,
        actor_email=user_email,
        actor_id=user_email,
        actor_kind=ActorKind.OWNER,
        architecture=ada_architecture(),
    )
    response = sse_response(_stream(running.transcript, after_sequence=0))
    response.headers["X-Turn-Id"] = running.turn.turn_id
    return response


@router.post("/{conversation_id}/connect", response_model=ConnectResponse)
async def connect(
    request: Request,
    body: ConnectRequest,
    target: Annotated[BuildTarget, Depends(resolve_build)],
) -> ConnectResponse:
    """The person's click on a Connect card. Their own action, never Ada's: installs the preset if needed and
    returns the sign-in address."""
    try:
        authorize_url = await start_connection(get_mcp_connector_service(), request.state.user_email, body.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ConnectResponse(authorize_url=authorize_url)


@router.get("/{conversation_id}/turns/active")
async def get_active_turn(target: Annotated[BuildTarget, Depends(resolve_build)]) -> ConversationTurnResponse | None:
    turn = ConversationTurnRepository().find_active(target.conversation.conversation_id)
    return turn.to_response() if turn else None


@router.get("/{conversation_id}/turns/{turn_id}/events")
async def stream_turn_events(turn: Annotated[ConversationTurn, Depends(resolve_build_turn)], after_sequence: int = 0):
    transcript = live_transcript(turn.turn_id)
    if transcript is None:
        raise HTTPException(status_code=410, detail="This response is no longer available.")
    return sse_response(_stream(transcript, after_sequence=after_sequence))


@router.post("/{conversation_id}/turns/{turn_id}/stop", status_code=204)
async def stop(turn: Annotated[ConversationTurn, Depends(resolve_build_turn)]) -> None:
    stop_turn(turn)


def _response(session: BuilderSession) -> BuilderSessionResponse:
    return BuilderSessionResponse(
        conversation_id=session.conversation_id,
        provider=session.provider,
        model=session.model,
        deployment_id=session.deployment_id,
        kit_id=session.kit_id,
        created_at=session.created_at,
    )
