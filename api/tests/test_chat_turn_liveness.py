from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.agents.turns.models import ConversationTurn, ConversationTurnStatus
from src.agents.turns.repository import ConversationTurnRepository
from src.config import settings

OWNER = "owner@example.com"


def _turn(
    *,
    conversation_id: str = "conv-1",
    agent_id: str = "agent-1",
    status: ConversationTurnStatus = ConversationTurnStatus.RUNNING,
    created_at: datetime | None = None,
    started_at: datetime | None = None,
    heartbeat_at: datetime | None = None,
) -> ConversationTurn:
    created = created_at or datetime(2026, 1, 1, tzinfo=timezone.utc)
    return ConversationTurn(
        conversation_id=conversation_id,
        agent_id=agent_id,
        created_by=OWNER,
        status=status,
        created_at=created,
        started_at=started_at if started_at is not None else created,
        last_heartbeat_at=heartbeat_at,
    )


def test_heartbeat_persists_last_heartbeat_at(dynamodb_table):
    repository = ConversationTurnRepository()
    turn = _turn()
    repository.create(turn)

    repository.heartbeat(turn)

    saved = repository.find_by_id(turn.turn_id)
    assert saved is not None
    assert saved.last_heartbeat_at is not None


def test_reaper_fails_abandoned_turn_without_writing_assistant_message(dynamodb_table, monkeypatch):
    monkeypatch.setattr(settings, "chat_turn_stale_timeout_seconds", 5 * 60)
    repository = ConversationTurnRepository()
    now = datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)
    abandoned = _turn(conversation_id="conv-abandoned", heartbeat_at=now - timedelta(minutes=10))
    repository.create(abandoned)

    failed_count = repository.fail_stale_turns(now=now)

    assert failed_count == 1
    saved = repository.find_by_id(abandoned.turn_id)
    assert saved is not None
    assert saved.status == ConversationTurnStatus.FAILED
    assert saved.error is not None
    assert saved.assistant_message_id is None


def test_reaper_leaves_fresh_and_terminal_turns_untouched(dynamodb_table, monkeypatch):
    monkeypatch.setattr(settings, "chat_turn_stale_timeout_seconds", 5 * 60)
    repository = ConversationTurnRepository()
    now = datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)
    fresh = _turn(conversation_id="conv-fresh", heartbeat_at=now - timedelta(minutes=1))
    terminal = _turn(
        conversation_id="conv-terminal",
        status=ConversationTurnStatus.SUCCEEDED,
        heartbeat_at=now - timedelta(minutes=30),
    )
    for turn in (fresh, terminal):
        repository.create(turn)

    failed_count = repository.fail_stale_turns(now=now)

    assert failed_count == 0
    saved_fresh = repository.find_by_id(fresh.turn_id)
    saved_terminal = repository.find_by_id(terminal.turn_id)
    assert saved_fresh is not None and saved_fresh.status == ConversationTurnStatus.RUNNING
    assert saved_terminal is not None and saved_terminal.status == ConversationTurnStatus.SUCCEEDED


def test_stale_transition_loses_race_to_newer_heartbeat(dynamodb_table):
    repository = ConversationTurnRepository()
    observed = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    turn = _turn(conversation_id="conv-race", heartbeat_at=observed)
    repository.create(turn)
    stale_snapshot = repository.find_by_id(turn.turn_id)
    assert stale_snapshot is not None

    repository.heartbeat(turn)  # a newer heartbeat lands between scan and write

    was_failed = repository._mark_failed_if_heartbeat_unchanged(
        stale_snapshot, failed_at=observed + timedelta(minutes=16)
    )

    assert was_failed is False
    saved = repository.find_by_id(turn.turn_id)
    assert saved is not None
    assert saved.status == ConversationTurnStatus.RUNNING


def test_is_stale_falls_back_through_heartbeat_started_created():
    now = datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)

    with_heartbeat = _turn(heartbeat_at=now - timedelta(minutes=10), started_at=now - timedelta(hours=1))
    assert with_heartbeat.is_stale(stale_after_seconds=5 * 60, now=now) is True

    without_heartbeat = _turn(started_at=now - timedelta(minutes=10), created_at=now - timedelta(hours=1))
    assert without_heartbeat.is_stale(stale_after_seconds=5 * 60, now=now) is True

    fresh = _turn(heartbeat_at=now - timedelta(minutes=1))
    assert fresh.is_stale(stale_after_seconds=5 * 60, now=now) is False

    not_running = _turn(status=ConversationTurnStatus.FAILED, heartbeat_at=now - timedelta(hours=1))
    assert not_running.is_stale(stale_after_seconds=5 * 60, now=now) is False
