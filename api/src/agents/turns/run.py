"""Detached execution of one chat turn.

`start_turn` hands the turn to `asyncio.create_task` and returns immediately.
The task is not part of the HTTP request's task tree, so a client disconnect
cannot reach it — see api/docs/LLD-async-chat-turns.md ("3. Driving the turn").
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.agents.architectures import get_agent_architecture
from src.agents.turns.models import ConversationTurn, ConversationTurnStatus
from src.agents.turns.repository import ConversationTurnRepository
from src.agents.turns.transcript import TurnTranscript, forget_transcript, live_transcript, open_transcript
from src.config import settings
from src.conversations.repository import ConversationRepository
from src.llm.events import SSEEvent, SSEEventType

if TYPE_CHECKING:
    from src.agents.models import Agent
    from src.conversations.models import Conversation
    from src.messages.models import Attachment

log = logging.getLogger(__name__)

_STOPPED_BY_USER = "Stopped by the user"


@dataclass(frozen=True)
class TurnRequest:
    """Everything a detached turn needs, all of it resolved before it starts."""

    agent: "Agent"
    conversation: "Conversation"
    user_message: str
    attachments: list["Attachment"] | None
    owner_email: str
    actor_email: str
    actor_id: str


def start_turn(
    *,
    agent: "Agent",
    conversation: "Conversation",
    user_message: str,
    attachments: list["Attachment"] | None,
    owner_email: str,
    actor_email: str,
    actor_id: str,
) -> ConversationTurn:
    now = datetime.now(timezone.utc)
    turn = ConversationTurn(
        conversation_id=conversation.conversation_id,
        agent_id=agent.agent_id,
        created_by=owner_email,
        created_at=now,
        started_at=now,
        last_heartbeat_at=now,
    )
    ConversationTurnRepository().create(turn)

    transcript = open_transcript(turn.turn_id)
    transcript.task = asyncio.create_task(
        _drive_turn(
            turn=turn,
            transcript=transcript,
            request=TurnRequest(
                agent=agent,
                conversation=conversation,
                user_message=user_message,
                attachments=attachments,
                owner_email=owner_email,
                actor_email=actor_email,
                actor_id=actor_id,
            ),
        )
    )
    return turn


def stop_turn(turn: ConversationTurn) -> None:
    """Cancel a live turn's task, or mark it cancelled if its process is gone."""
    transcript = live_transcript(turn.turn_id)
    if transcript and transcript.task and not transcript.task.done():
        transcript.task.cancel()
        return
    ConversationTurnRepository().finish(
        turn, ConversationTurnStatus.CANCELLED, error=_STOPPED_BY_USER
    )


async def _drive_turn(
    *,
    turn: ConversationTurn,
    transcript: TurnTranscript,
    request: TurnRequest,
) -> None:
    turn_repo = ConversationTurnRepository()
    heartbeat_task = asyncio.create_task(_keep_heartbeat(turn, turn_repo))
    failed_error: str | None = None

    try:
        architecture = get_agent_architecture(request.agent.agent_architecture)
        async for event in architecture.handle_message(  # pyright: ignore[reportGeneralTypeIssues]
            agent=request.agent,
            conversation=request.conversation,
            user_message=request.user_message,
            owner_email=request.owner_email,
            actor_email=request.actor_email,
            actor_id=request.actor_id,
            attachments=request.attachments,
        ):
            transcript.record(event)
            if event.event_type == SSEEventType.USER_MESSAGE_SAVED:
                turn.user_message_id = event.message_id
            elif event.event_type == SSEEventType.ASSISTANT_MESSAGE_SAVED:
                turn.assistant_message_id = event.message_id
            elif event.event_type == SSEEventType.ERROR:
                failed_error = event.content

        turn_repo.finish(
            turn,
            ConversationTurnStatus.FAILED if failed_error else ConversationTurnStatus.SUCCEEDED,
            error=failed_error,
            assistant_message_id=turn.assistant_message_id,
        )
    except asyncio.CancelledError:
        turn_repo.finish(turn, ConversationTurnStatus.CANCELLED, error=_STOPPED_BY_USER)
        raise
    except Exception as exc:
        log.error("Chat turn %s failed: %s", turn.turn_id, exc, exc_info=True)
        transcript.record(SSEEvent(event_type=SSEEventType.ERROR, content=str(exc)))
        turn_repo.finish(turn, ConversationTurnStatus.FAILED, error=str(exc))
    finally:
        # The user sent a message either way, so the conversation counts as
        # active on every outcome -- including the ones that used to skip this.
        _touch_conversation(request.conversation)
        heartbeat_task.cancel()
        transcript.finish()
        asyncio.get_running_loop().call_later(
            settings.chat_turn_transcript_grace_seconds, forget_transcript, turn.turn_id
        )


def _touch_conversation(conversation: "Conversation") -> None:
    """Best-effort: a failed sidebar timestamp must not fail the turn."""
    try:
        ConversationRepository().touch(conversation)
    except Exception:
        log.warning(
            "Failed to bump updated_at for conversation %s",
            conversation.conversation_id,
            exc_info=True,
        )


async def _keep_heartbeat(turn: ConversationTurn, turn_repo: ConversationTurnRepository) -> None:
    """A plain liveness ticker — deliberately not tied to LLM/tool activity.

    There is no wall-clock budget on a turn. What must be detected is "no task
    is processing this record any more", not "the LLM is slow"; an
    event-driven heartbeat would stop beating during a legitimate long tool
    call and the reaper would kill a live turn.
    """
    while True:
        await asyncio.sleep(settings.chat_turn_heartbeat_interval_seconds)
        turn_repo.heartbeat(turn)
