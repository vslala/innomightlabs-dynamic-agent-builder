"""
Building with Ila.

Endpoints:
    GET  /builder/session-form                          Provider and model to build with (a SchemaForm)
    POST /builder/sessions                              Start a building conversation, greeted by Ila
    GET  /builder/sessions                              The person's building conversations
    POST /builder/{conversation_id}/send-message        A turn with Ila (SSE, like an agent's send-message)
    GET  /builder/{conversation_id}/turns/active        The running turn, to reattach
    GET  /builder/{conversation_id}/turns/{id}/events   Tail a turn's transcript
    POST /builder/{conversation_id}/turns/{id}/stop     Stop a turn

The chat routes mirror an agent's, so the dashboard chat works for Ila unchanged.
"""

import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel

import src.form_models as form_models
from src.iam.dependencies import get_owner, get_principal
from src.agents.schemas import get_create_agent_form
from src.agents.service import validate_provider_model
from src.agents.turns import ConversationTurn, ConversationTurnRepository, ConversationTurnResponse
from src.agents.turns import live_transcript, start_turn, stop_turn
from src.builder.ila import ILA_AGENT_ID, GREETING, ila_agent, ila_architecture
from src.builder.connections import start_connection
from src.builder.models import BuilderSession, BuilderSessionResponse, CreateBuilderSessionRequest
from src.builder.repository import BuilderSessionRepository
from src.common.sse import sse_response
from src.consent.models import ConsentDecisionRequest, ConsentRequestResponse
from src.consent.router import decide_and_carry_on, list_conversation_consents
from src.connectors.mcp.service import get_mcp_connector_service
from src.conversations.models import Conversation
from src.conversations.repository import ConversationRepository
from src.form_options import FormOptionsContext, hydrate_form_options
from src.messages.models import Message
from src.messages.repositories import get_message_repository
from src.settings.access import settings_manager
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
    #: Where the sign-in comes back to; the web popup's page when absent. Checked with safe_return_to.
    return_to: str | None = None


class ConnectResponse(BaseModel):
    #: Where to sign in, in a popup. None when the account is already connected.
    authorize_url: str | None = None


@dataclass(frozen=True)
class BuildTarget:
    session: BuilderSession
    conversation: Conversation


def resolve_build(request: Request, conversation_id: str) -> BuildTarget:
    owner = get_owner(request)
    session = BuilderSessionRepository().find(owner.member_pk, conversation_id)
    conversation = ConversationRepository().find_by_id(conversation_id, owner.member_pk)
    if session is None or conversation is None:
        raise HTTPException(status_code=404, detail="Building session not found")
    return BuildTarget(session=session, conversation=conversation)


def resolve_build_turn(turn_id: str, target: Annotated[BuildTarget, Depends(resolve_build)]) -> ConversationTurn:
    turn = ConversationTurnRepository().find_by_id(turn_id)
    if not turn or turn.conversation_id != target.conversation.conversation_id:
        raise HTTPException(status_code=404, detail="Turn not found")
    return turn


@router.get("/session-form", response_model=form_models.Form, response_model_exclude_none=True)
async def session_form(request: Request) -> form_models.Form:
    """The person's own providers and models, filled in the same way as the create-agent form."""
    inputs = [field for field in get_create_agent_form().form_inputs if field.name in SESSION_FORM_FIELDS]
    form = form_models.Form(form_name="Build with Ila", submit_path="/builder/sessions", form_inputs=inputs)
    owner = get_owner(request)
    return hydrate_form_options(form, FormOptionsContext(owner=owner))


@router.post("/sessions", response_model=BuilderSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(request: Request, body: CreateBuilderSessionRequest) -> BuilderSessionResponse:
    user_email: str = request.state.user_email
    owner = get_owner(request)
    model = body.agent_model or None
    try:
        validate_provider_model(owner, body.agent_provider, model)
    except ValueError:
        raise HTTPException(status_code=400, detail="Choose a provider and model your account has set up.")
    if not get_provider_settings_repository().find_by_provider(owner.account_id, body.agent_provider):
        raise HTTPException(
            status_code=400,
            detail=f"An account admin needs to set up {body.agent_provider} in Settings > Provider Configuration first.",
        )

    conversation = ConversationRepository().save(Conversation(
        title="Building with Ila", agent_id=ILA_AGENT_ID, account_id=owner.account_id, created_by=owner.user_id,
    ))
    session = BuilderSessionRepository().save(BuilderSession(
        conversation_id=conversation.conversation_id,
        account_id=owner.account_id,
        user_id=owner.user_id,
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
    return [_response(session) for session in BuilderSessionRepository().list_in(get_owner(request).member_pk)]


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
            detail={"message": "Ila is still working on your last message.", "turn_id": active.turn_id},
        )
    running = start_turn(
        agent=ila_agent(target.session),
        conversation=target.conversation,
        user_message=body.content,
        attachments=None,
        owner_email=user_email,
        actor_email=user_email,
        actor_id=user_email,
        actor_kind=ActorKind.OWNER,
        architecture=ila_architecture(),
    )
    response = sse_response(running.transcript.as_sse())
    response.headers["X-Turn-Id"] = running.turn.turn_id
    return response


@router.get("/{conversation_id}/consents")
async def list_consents(target: Annotated[BuildTarget, Depends(resolve_build)]) -> list[ConsentRequestResponse]:
    """The consent cards in Ila's chat, such as the steps of an automation she built, and where each stands."""
    return list_conversation_consents(target.conversation.conversation_id, ila_agent(target.session).agent_id)


@router.post("/{conversation_id}/consents/{consent_id}/decision")
async def decide(
    request: Request,
    consent_id: str,
    body: ConsentDecisionRequest,
    target: Annotated[BuildTarget, Depends(resolve_build)],
):
    """As an agent chat's decision: record it, then Ila carries on from the card."""
    user_email: str = request.state.user_email
    return decide_and_carry_on(
        consent_id,
        body,
        agent=ila_agent(target.session),
        conversation=target.conversation,
        caller=get_owner(request),
        owner_email=user_email,
        architecture=ila_architecture(),
    )


@router.post("/{conversation_id}/connect", response_model=ConnectResponse)
async def connect(
    request: Request,
    body: ConnectRequest,
    target: Annotated[BuildTarget, Depends(resolve_build)],
) -> ConnectResponse:
    """The person's click on a Connect card. Their own action, never Ila's: installs the preset if needed and
    returns the sign-in address. The connection becomes the account's, so it takes an admin."""
    principal = settings_manager(get_principal(request))
    try:
        authorize_url = await start_connection(
            get_mcp_connector_service(), principal.account_id, request.state.user_email, body.provider,
            body.return_to,
        )
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
    return sse_response(transcript.as_sse(after_sequence=after_sequence))


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
