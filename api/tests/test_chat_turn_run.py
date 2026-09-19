from __future__ import annotations

import asyncio
from typing import AsyncIterator

from src.agents.architectures.base import AgentArchitecture
from src.agents.models import Agent
from src.agents.turns.models import ConversationTurnStatus
from src.agents.turns.repository import ConversationTurnRepository
from src.agents.turns.run import start_turn, stop_turn
from src.agents.turns.transcript import live_transcript
from src.config import settings
from src.conversations.models import Conversation
from src.conversations.repository import ConversationRepository
from src.llm.events import SSEEvent, SSEEventType

OWNER = "owner@example.com"


def _agent(name: str = "Test Agent") -> Agent:
    return Agent(
        agent_name=name,
        agent_architecture="fake",
        agent_provider="Bedrock",
        agent_persona="Helpful",
        created_by=OWNER,
    )


def _seeded_conversation(agent: Agent) -> Conversation:
    conversation = Conversation(title="Test Conversation", agent_id=agent.agent_id, created_by=OWNER)
    return ConversationRepository().save(conversation)


class FixedArchitecture(AgentArchitecture):
    """Runs to completion without pausing; content derived from its arguments so
    concurrent turns never mix up which response belongs to which conversation."""

    async def handle_message(
        self, agent, conversation, user_message, owner_email, actor_email, actor_id, attachments=None
    ) -> AsyncIterator[SSEEvent]:
        yield SSEEvent(
            event_type=SSEEventType.USER_MESSAGE_SAVED,
            content="saved",
            message_id=f"user-{conversation.conversation_id}",
        )
        yield SSEEvent(
            event_type=SSEEventType.AGENT_RESPONSE_TO_USER,
            content=f"hello from {agent.agent_id}",
        )
        yield SSEEvent(
            event_type=SSEEventType.ASSISTANT_MESSAGE_SAVED,
            content="saved",
            message_id=f"assistant-{conversation.conversation_id}",
        )
        yield SSEEvent(event_type=SSEEventType.STREAM_COMPLETE, content="done")

    @property
    def name(self) -> str:
        return "fixed"


class ControllableArchitecture(AgentArchitecture):
    """Pauses after its first response chunk until `resume` is set, so tests can
    disconnect mid-turn and reattach while the turn is provably still running."""

    def __init__(self) -> None:
        self.resume = asyncio.Event()

    async def handle_message(
        self, agent, conversation, user_message, owner_email, actor_email, actor_id, attachments=None
    ) -> AsyncIterator[SSEEvent]:
        yield SSEEvent(event_type=SSEEventType.USER_MESSAGE_SAVED, content="saved", message_id="user-1")
        yield SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content="hello ")
        await self.resume.wait()
        yield SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content="world")
        yield SSEEvent(
            event_type=SSEEventType.ASSISTANT_MESSAGE_SAVED, content="saved", message_id="assistant-1"
        )
        yield SSEEvent(event_type=SSEEventType.STREAM_COMPLETE, content="done")

    @property
    def name(self) -> str:
        return "controllable"


class FailingArchitecture(AgentArchitecture):
    async def handle_message(
        self, agent, conversation, user_message, owner_email, actor_email, actor_id, attachments=None
    ) -> AsyncIterator[SSEEvent]:
        yield SSEEvent(event_type=SSEEventType.USER_MESSAGE_SAVED, content="saved", message_id="user-1")
        yield SSEEvent(event_type=SSEEventType.ERROR, content="the model provider is unavailable")

    @property
    def name(self) -> str:
        return "failing"


def _patch_architecture(monkeypatch, architecture: AgentArchitecture) -> None:
    monkeypatch.setattr("src.agents.turns.run.get_agent_architecture", lambda *_a, **_kw: architecture)


async def test_turn_completes_after_subscriber_disconnects(dynamodb_table, monkeypatch):
    _patch_architecture(monkeypatch, FixedArchitecture())
    agent = _agent()
    conversation = _seeded_conversation(agent)

    turn = start_turn(
        agent=agent,
        conversation=conversation,
        user_message="hi",
        attachments=None,
        owner_email=OWNER,
        actor_email=OWNER,
        actor_id=OWNER,
    )
    transcript = live_transcript(turn.turn_id)
    assert transcript is not None

    received = []
    async for _sequence, event in transcript.follow():
        received.append(event)
        if len(received) == 2:
            break  # simulates Starlette closing the response generator on disconnect

    await asyncio.wait_for(transcript.task, timeout=2)

    saved_turn = ConversationTurnRepository().find_by_id(turn.turn_id)
    assert saved_turn is not None
    assert saved_turn.status == ConversationTurnStatus.SUCCEEDED
    assert saved_turn.assistant_message_id == f"assistant-{conversation.conversation_id}"

    saved_conversation = ConversationRepository().find_by_id(conversation.conversation_id, OWNER)
    assert saved_conversation is not None
    assert saved_conversation.updated_at is not None


async def test_reattach_replays_from_zero_then_follows_live(dynamodb_table, monkeypatch):
    architecture = ControllableArchitecture()
    _patch_architecture(monkeypatch, architecture)
    agent = _agent()
    conversation = _seeded_conversation(agent)

    turn = start_turn(
        agent=agent,
        conversation=conversation,
        user_message="hi",
        attachments=None,
        owner_email=OWNER,
        actor_email=OWNER,
        actor_id=OWNER,
    )
    transcript = live_transcript(turn.turn_id)
    assert transcript is not None

    first_pass: list[SSEEventType] = []
    async for _sequence, event in transcript.follow(after_sequence=0):
        first_pass.append(event.event_type)
        if len(first_pass) == 4:  # 2 lifecycle notices, USER_MESSAGE_SAVED, first text chunk
            break

    architecture.resume.set()

    replay: list[SSEEventType] = []
    async for _sequence, event in transcript.follow(after_sequence=0):
        replay.append(event.event_type)

    await asyncio.wait_for(transcript.task, timeout=2)

    assert replay[:4] == first_pass
    assert replay[-1] == SSEEventType.STREAM_COMPLETE
    assert len(replay) > len(first_pass)


async def test_two_concurrent_turns_do_not_interfere(dynamodb_table, monkeypatch):
    _patch_architecture(monkeypatch, FixedArchitecture())
    agent_a, agent_b = _agent("Agent A"), _agent("Agent B")
    conversation_a, conversation_b = _seeded_conversation(agent_a), _seeded_conversation(agent_b)

    turn_a = start_turn(
        agent=agent_a,
        conversation=conversation_a,
        user_message="hi a",
        attachments=None,
        owner_email=OWNER,
        actor_email=OWNER,
        actor_id=OWNER,
    )
    turn_b = start_turn(
        agent=agent_b,
        conversation=conversation_b,
        user_message="hi b",
        attachments=None,
        owner_email=OWNER,
        actor_email=OWNER,
        actor_id=OWNER,
    )

    transcript_a = live_transcript(turn_a.turn_id)
    transcript_b = live_transcript(turn_b.turn_id)
    assert transcript_a is not None and transcript_b is not None
    await asyncio.wait_for(asyncio.gather(transcript_a.task, transcript_b.task), timeout=2)

    events_a = [event async for _sequence, event in transcript_a.follow()]
    events_b = [event async for _sequence, event in transcript_b.follow()]

    text_a = next(e.content for e in events_a if e.event_type == SSEEventType.AGENT_RESPONSE_TO_USER)
    text_b = next(e.content for e in events_b if e.event_type == SSEEventType.AGENT_RESPONSE_TO_USER)
    assert text_a == f"hello from {agent_a.agent_id}"
    assert text_b == f"hello from {agent_b.agent_id}"

    turn_repo = ConversationTurnRepository()
    saved_a = turn_repo.find_by_id(turn_a.turn_id)
    saved_b = turn_repo.find_by_id(turn_b.turn_id)
    assert saved_a is not None and saved_a.status == ConversationTurnStatus.SUCCEEDED
    assert saved_b is not None and saved_b.status == ConversationTurnStatus.SUCCEEDED
    assert saved_a.assistant_message_id == f"assistant-{conversation_a.conversation_id}"
    assert saved_b.assistant_message_id == f"assistant-{conversation_b.conversation_id}"


async def test_find_active_turn_reflects_running_state(dynamodb_table, monkeypatch):
    architecture = ControllableArchitecture()
    _patch_architecture(monkeypatch, architecture)
    agent = _agent()
    conversation = _seeded_conversation(agent)
    turn_repo = ConversationTurnRepository()

    turn = start_turn(
        agent=agent,
        conversation=conversation,
        user_message="hi",
        attachments=None,
        owner_email=OWNER,
        actor_email=OWNER,
        actor_id=OWNER,
    )

    active = turn_repo.find_active(conversation.conversation_id)
    assert active is not None
    assert active.turn_id == turn.turn_id

    architecture.resume.set()
    transcript = live_transcript(turn.turn_id)
    assert transcript is not None
    await asyncio.wait_for(transcript.task, timeout=2)

    assert turn_repo.find_active(conversation.conversation_id) is None


async def test_architecture_error_event_marks_turn_failed_and_terminates_followers(
    dynamodb_table, monkeypatch
):
    _patch_architecture(monkeypatch, FailingArchitecture())
    agent = _agent()
    conversation = _seeded_conversation(agent)

    turn = start_turn(
        agent=agent,
        conversation=conversation,
        user_message="hi",
        attachments=None,
        owner_email=OWNER,
        actor_email=OWNER,
        actor_id=OWNER,
    )
    transcript = live_transcript(turn.turn_id)
    assert transcript is not None

    events = [event async for _sequence, event in transcript.follow()]

    assert events[-1].event_type == SSEEventType.ERROR
    saved_turn = ConversationTurnRepository().find_by_id(turn.turn_id)
    assert saved_turn is not None
    assert saved_turn.status == ConversationTurnStatus.FAILED
    assert saved_turn.error == "the model provider is unavailable"


async def test_stop_turn_cancels_task_and_marks_cancelled(dynamodb_table, monkeypatch):
    architecture = ControllableArchitecture()
    _patch_architecture(monkeypatch, architecture)
    agent = _agent()
    conversation = _seeded_conversation(agent)

    turn = start_turn(
        agent=agent,
        conversation=conversation,
        user_message="hi",
        attachments=None,
        owner_email=OWNER,
        actor_email=OWNER,
        actor_id=OWNER,
    )
    transcript = live_transcript(turn.turn_id)
    assert transcript is not None

    # Let the turn reach its genuine suspension point (mid-stream) before stopping it.
    # Cancelling a task before its first scheduling tick never runs its except/finally
    # blocks at all (a plain asyncio behavior, not specific to this design), so a
    # realistic "stop" test targets a turn that is provably already running.
    received = []
    async for _sequence, event in transcript.follow():
        received.append(event)
        if len(received) == 2:
            break

    stop_turn(turn)
    # `_drive_turn` re-raises CancelledError after persisting the CANCELLED status, so
    # the cancelled task itself surfaces that exception to whoever awaits it — expected,
    # not a failure; production code never awaits `transcript.task` after stopping it.
    try:
        await asyncio.wait_for(transcript.task, timeout=2)
    except asyncio.CancelledError:
        pass

    saved_turn = ConversationTurnRepository().find_by_id(turn.turn_id)
    assert saved_turn is not None
    assert saved_turn.status == ConversationTurnStatus.CANCELLED


async def test_transcript_is_forgotten_after_grace_window_while_follower_keeps_streaming(
    dynamodb_table, monkeypatch
):
    monkeypatch.setattr(settings, "chat_turn_transcript_grace_seconds", 0.05)
    _patch_architecture(monkeypatch, FixedArchitecture())
    agent = _agent()
    conversation = _seeded_conversation(agent)

    turn = start_turn(
        agent=agent,
        conversation=conversation,
        user_message="hi",
        attachments=None,
        owner_email=OWNER,
        actor_email=OWNER,
        actor_id=OWNER,
    )
    transcript = live_transcript(turn.turn_id)
    assert transcript is not None
    await asyncio.wait_for(transcript.task, timeout=2)

    await asyncio.sleep(0.2)
    assert live_transcript(turn.turn_id) is None

    events = [event async for _sequence, event in transcript.follow()]
    assert events[-1].event_type == SSEEventType.STREAM_COMPLETE
