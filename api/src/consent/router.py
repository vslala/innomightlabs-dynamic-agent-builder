"""Consent cards in a chat, the person's decision on one, and what they always allow an agent to do.

See docs/LLD-action-consent.md.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.agents.access import own_agent_with, owner_of
from src.agents.architectures.base import AgentArchitecture
from src.agents.models import Agent
from src.agents.router import ChatTarget, resolve_chat_target
from src.agents.turns import ConversationTurnRepository, start_turn
from src.common.sse import sse_response
from src.consent.actions import consent_actions
from src.consent.continuation import ConsentContinuation
from src.consent.models import ConsentDecisionRequest, ConsentRequestResponse, StandingConsent
from src.consent.repository import ConsentRepository, ConsentStateChanged
from src.conversations.models import Conversation
from src.iam.dependencies import get_owner
from src.accounts.owner import Owner
from src.skills.models import ActorKind

router = APIRouter(prefix="/agents", tags=["consent"])


@router.get("/{agent_id}/{conversation_id}/consents")
async def list_consents(target: Annotated[ChatTarget, Depends(resolve_chat_target)]) -> list[ConsentRequestResponse]:
    """Every consent card in the conversation and where it stands, so the chat can show them after a reload."""
    return list_conversation_consents(target.conversation.conversation_id, target.agent.agent_id)


@router.post("/{agent_id}/{conversation_id}/consents/{consent_id}/decision")
async def decide(
    consent_id: str,
    body: ConsentDecisionRequest,
    target: Annotated[ChatTarget, Depends(resolve_chat_target)],
):
    """Approve (with edits, or always) or reject a card, then run the turn that carries on from it.

    Streams that turn like send-message, with its `X-Turn-Id`. 409 while another turn is running, or when the card
    was already decided.
    """
    return decide_and_carry_on(
        consent_id,
        body,
        agent=target.agent,
        conversation=target.conversation,
        caller=target.caller,
        owner_email=owner_of(target.agent).email,
    )


def decide_and_carry_on(
    consent_id: str,
    body: ConsentDecisionRequest,
    *,
    agent: Agent,
    conversation: Conversation,
    caller: Owner,
    owner_email: str,
    architecture: AgentArchitecture | None = None,
):
    """Record the person's decision on a card in this conversation, and start the turn that carries on from it.

    Shared by the agents' chat and Ila's (`architecture`), which differ only in how they find the conversation.
    """
    repository = ConsentRepository()
    request = repository.get(consent_id)
    if request is None or request.conversation_id != conversation.conversation_id or request.agent_id != agent.agent_id:
        raise HTTPException(status_code=404, detail="Approval not found")
    # Only the person the action would act for decides: the agent's owner, who raised it
    if request.owner_id != caller.user_id:
        raise HTTPException(status_code=403, detail="Only the agent's owner can decide this")
    if not request.is_open():
        raise HTTPException(status_code=409, detail="This approval was already decided, replaced or expired.")
    if body.always and request.subject.kind == "automation_steps":
        raise HTTPException(status_code=400, detail="A step's approval already lasts; there is nothing to always allow.")
    active_turn = ConversationTurnRepository().find_active(conversation.conversation_id)
    if active_turn:
        raise HTTPException(
            status_code=409,
            detail={"message": "This conversation already has a response in progress.", "turn_id": active_turn.turn_id},
        )

    approve = body.decision == "approve"
    try:
        edits = request.checked_edits(body.edits) if approve else {}
        request = repository.decide(
            request, approve=approve, by=caller.user_id, edits=edits, always=body.always, reason=body.reason
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConsentStateChanged as exc:
        raise HTTPException(status_code=409, detail="This approval was already decided.") from exc
    if request.always:
        repository.save_standing(
            StandingConsent(
                agent_id=request.agent_id,
                key=request.key,
                title=request.title,
                granted_by=caller.user_id,
                consent_id=request.consent_id,
            )
        )

    running = start_turn(
        agent=agent,
        conversation=conversation,
        user_message="",
        attachments=[],
        owner_email=owner_email,
        actor_email=caller.email,
        actor_id=caller.email,
        actor_kind=ActorKind.OWNER,
        architecture=architecture,
        prelude=ConsentContinuation(request.consent_id, agent),
    )
    response = sse_response(running.transcript.as_sse())
    response.headers["X-Turn-Id"] = running.turn.turn_id
    return response


def list_conversation_consents(conversation_id: str, agent_id: str) -> list[ConsentRequestResponse]:
    repository = ConsentRepository()
    requests = repository.list_for_conversation(conversation_id)
    return [request.to_response(repository.image_url) for request in requests if request.agent_id == agent_id]


class ConsentActionResponse(BaseModel):
    """One action the agent asks about first, and whether the owner always allows it."""

    key: str
    title: str
    warning: str | None = None
    #: The skill (or MCP connection) it belongs to, as the agent's skills list names it.
    source: str
    always_allowed: bool


@router.get("/{agent_id}/standing-consents")
async def list_standing_consents(
    agent: Annotated[Agent, Depends(own_agent_with("agents:Get"))],
) -> list[ConsentActionResponse]:
    """The agent's actions that ask first, each with whether the owner said "always allow"."""
    allowed = {consent.key for consent in ConsentRepository().list_standing(agent.agent_id)}
    return [
        ConsentActionResponse(
            key=action.key, title=action.title, warning=action.warning, source=action.source,
            always_allowed=action.key in allowed,
        )
        for action in consent_actions(agent.agent_id, agent.account_id)
    ]


@router.put("/{agent_id}/standing-consents/{key}", status_code=204)
async def always_allow(
    key: str,
    agent: Annotated[Agent, Depends(own_agent_with("agents:Update"))],
    caller: Annotated[Owner, Depends(get_owner)],
) -> None:
    found = next((action for action in consent_actions(agent.agent_id, agent.account_id) if action.key == key), None)
    if found is None:
        raise HTTPException(status_code=404, detail="This agent has no such action that asks first")
    ConsentRepository().save_standing(
        StandingConsent(agent_id=agent.agent_id, key=key, title=found.title, granted_by=caller.user_id)
    )


@router.delete("/{agent_id}/standing-consents/{key}", status_code=204)
async def ask_every_time(
    key: str,
    agent: Annotated[Agent, Depends(own_agent_with("agents:Update"))],
) -> None:
    ConsentRepository().forget_standing(agent.agent_id, key)
