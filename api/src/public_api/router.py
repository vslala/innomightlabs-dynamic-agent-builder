"""The public /v1 API: chat with one agent using that agent's secret key.

A key acts as the agent's owner — same provider settings, skills, knowledge
bases and tools as a dashboard chat — but its conversations live in the key's
own partition and its memory is scoped to the key (or to an end user of it).
See docs/LLD-public-api-and-embeddable-widget.md.
"""

from dataclasses import dataclass
from typing import Annotated, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query

from src.agents.turns import ConversationTurnRepository, live_transcript, start_turn
from src.agents.turns.transcript import TurnTranscript
from src.common.pagination import Paginated
from src.common.sse import sse_response
from src.conversations.models import ApiConversation
from src.conversations.repository import ConversationRepository
from src.conversations.router import find_visible_messages_newest_first
from src.public_api.auth import PublicApiCaller, require_secret_key
from src.public_api.events import collect_invocation, stream_public_events
from src.public_api.models import (
    V1AgentResponse,
    V1ConversationResponse,
    V1CreateConversationRequest,
    V1MessageResponse,
    V1SendMessageRequest,
    V1SendMessageResponse,
)
from src.skills.models import ActorKind

router = APIRouter(prefix="/v1/agents/{agent_id}", tags=["public-api"])

Caller = Annotated[PublicApiCaller, Depends(require_secret_key)]


@dataclass(frozen=True)
class V1ChatTarget:
    caller: PublicApiCaller
    conversation: ApiConversation


def resolve_conversation(conversation_id: str, caller: Caller) -> V1ChatTarget:
    """Load a conversation that genuinely belongs to this key and agent."""
    conversation = ConversationRepository().find_by_id(conversation_id, ApiConversation.owner_for(caller.key.key_id))
    if not isinstance(conversation, ApiConversation) or conversation.agent_id != caller.agent.agent_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return V1ChatTarget(caller=caller, conversation=conversation)


Target = Annotated[V1ChatTarget, Depends(resolve_conversation)]


@router.get("", response_model=V1AgentResponse)
async def get_agent(caller: Caller) -> V1AgentResponse:
    return V1AgentResponse.of(caller.agent)


@router.post("/conversations", response_model=V1ConversationResponse, status_code=201)
async def create_conversation(body: V1CreateConversationRequest, caller: Caller) -> V1ConversationResponse:
    conversation = ApiConversation.start(
        api_key_id=caller.key.key_id,
        agent_id=caller.agent.agent_id,
        title=body.title or f"Chat with {caller.agent.agent_name}",
        end_user_id=body.end_user_id,
    )
    ConversationRepository().save(conversation)
    return V1ConversationResponse.of(conversation)


@router.get("/conversations", response_model=Paginated[V1ConversationResponse])
async def list_conversations(
    caller: Caller,
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
) -> Paginated[V1ConversationResponse]:
    """This key's conversations with the agent, most recently active first."""
    conversations, next_cursor, has_more = ConversationRepository().find_all_by_user_paginated(
        ApiConversation.owner_for(caller.key.key_id), limit=limit, cursor=cursor
    )
    return Paginated[V1ConversationResponse](
        items=[
            V1ConversationResponse.of(conversation)
            for conversation in conversations
            if isinstance(conversation, ApiConversation)
        ],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/conversations/{conversation_id}", response_model=V1ConversationResponse)
async def get_conversation(target: Target) -> V1ConversationResponse:
    return V1ConversationResponse.of(target.conversation)


@router.get("/conversations/{conversation_id}/messages", response_model=Paginated[V1MessageResponse])
async def list_messages(
    target: Target,
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
) -> Paginated[V1MessageResponse]:
    """User and assistant messages, newest first."""
    messages, next_cursor, has_more = find_visible_messages_newest_first(
        target.conversation.conversation_id, limit=limit, cursor=cursor
    )
    return Paginated[V1MessageResponse](
        items=[V1MessageResponse.of(message) for message in messages],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.post("/conversations/{conversation_id}/messages", response_model=V1SendMessageResponse)
async def send_message(body: V1SendMessageRequest, target: Target):
    """Send a message to the agent.

    With `stream` (the default) the reply streams as Server-Sent Events:
    `message.created`, `message.delta`, `tool.started`, `tool.completed`,
    `message.completed`, then `done` — or `error`. Without it, the request waits
    for the whole reply. Either way the turn runs to completion server-side even
    if the connection drops, and its id is in the `X-Turn-Id` header.

    A second message while a reply is still in progress is rejected with 409.
    """
    conversation = target.conversation
    active_turn = ConversationTurnRepository().find_active(conversation.conversation_id)
    if active_turn:
        raise HTTPException(
            status_code=409,
            detail={"message": "A response is already in progress.", "turn_id": active_turn.turn_id},
        )

    owner_email = target.caller.owner_email
    turn = start_turn(
        agent=target.caller.agent,
        conversation=conversation,
        user_message=body.content,
        attachments=[],
        owner_email=owner_email,
        actor_email=owner_email,
        actor_id=conversation.actor_id,
        actor_kind=ActorKind.API,
        api_key_id=target.caller.key.key_id,
    )
    transcript = cast(TurnTranscript, live_transcript(turn.turn_id))

    if body.stream:
        response = sse_response(stream_public_events(transcript))
        response.headers["X-Turn-Id"] = turn.turn_id
        return response

    result = await collect_invocation(transcript)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "Agent invocation failed")
    return V1SendMessageResponse(
        conversation_id=conversation.conversation_id,
        turn_id=turn.turn_id,
        user_message_id=result.user_message_id,
        assistant_message_id=result.assistant_message_id,
        text=result.response_text,
    )
