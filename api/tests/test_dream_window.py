from datetime import datetime, timedelta, timezone

from src.conversations.models import AutomationConversation, Conversation
from src.dream.models import DreamCursor, DreamSettings
from src.dream.window import DreamWindowBuilder
from src.messages.models import Message
from src.messages.repositories.in_memory import InMemoryMessageRepository


OWNER = "owner@example.com"
AGENT_ID = "agent-1"
NOW = datetime(2026, 2, 1, 12, tzinfo=timezone.utc)


class ConversationRepositoryStub:
    def __init__(self, conversations: list[Conversation]):
        self.conversations = conversations

    def find_all_by_user(self, owner_email: str) -> list[Conversation]:
        assert owner_email == OWNER
        return self.conversations


class TrackingMessageRepository(InMemoryMessageRepository):
    def __init__(self) -> None:
        super().__init__()
        self.probed_conversation_ids: list[str] = []
        self.paged_conversation_ids: list[str] = []

    def has_messages_after(self, conversation_id: str, after: datetime) -> bool:
        self.probed_conversation_ids.append(conversation_id)
        return super().has_messages_after(conversation_id, after)

    def find_by_conversation_paginated(
        self, conversation_id: str, limit: int = 50, cursor: str | None = None
    ) -> tuple[list[Message], str | None, bool]:
        self.paged_conversation_ids.append(conversation_id)
        return super().find_by_conversation_paginated(conversation_id, limit, cursor)


def conversation(conversation_id: str, *, agent_id: str = AGENT_ID) -> Conversation:
    return Conversation(
        conversation_id=conversation_id,
        title=conversation_id,
        agent_id=agent_id,
        created_by=OWNER,
        created_at=NOW - timedelta(days=40),
    )


def message(conversation_id: str, message_id: str, created_at: datetime) -> Message:
    return Message(
        message_id=message_id,
        conversation_id=conversation_id,
        role="user",
        content=message_id,
        created_at=created_at,
    )


def build_window(
    conversations: list[Conversation],
    repository: TrackingMessageRepository,
    *,
    cursor: DreamCursor | None = None,
    timeout_minutes: int = 60,
    backfill_days: int = 30,
):
    return DreamWindowBuilder(
        conversation_repository=ConversationRepositoryStub(conversations),
        message_repository=repository,
        page_size=1,
    ).build(
        agent_id=AGENT_ID,
        owner_email=OWNER,
        session_timeout_minutes=timeout_minutes,
        settings=DreamSettings(user_email=OWNER, backfill_days=backfill_days),
        cursor=cursor,
        now=NOW,
    )


def test_no_new_traffic_skips_paging_and_returns_an_empty_window():
    repository = TrackingMessageRepository()
    item = conversation("old")
    cursor = DreamCursor(
        agent_id=AGENT_ID,
        user_id=OWNER,
        last_session_ended_at=NOW - timedelta(days=1),
        backfill_completed=True,
    )
    repository.save(message(item.conversation_id, "old-message", NOW - timedelta(days=2)))

    window = build_window([item], repository, cursor=cursor)

    assert window.mode == "daily"
    assert window.sessions == []
    assert repository.probed_conversation_ids == [item.conversation_id]
    assert repository.paged_conversation_ids == []


def test_new_but_open_session_is_excluded_from_the_window():
    repository = TrackingMessageRepository()
    item = conversation("open")
    repository.save(message(item.conversation_id, "recent", NOW - timedelta(minutes=30)))

    window = build_window([item], repository)

    assert window.sessions == []
    assert repository.paged_conversation_ids == [item.conversation_id]
    assert window.end == NOW - timedelta(hours=1)


def test_backfill_start_is_capped_at_the_configured_floor():
    repository = TrackingMessageRepository()
    item = conversation("backfill")
    floor = NOW - timedelta(days=30)
    repository.save(message(item.conversation_id, "before-floor", floor - timedelta(hours=2)))
    repository.save(message(item.conversation_id, "after-floor", floor + timedelta(hours=2)))

    window = build_window([item], repository)

    assert window.mode == "backfill"
    assert window.start == floor
    assert [session.messages[-1].message_id for session in window.sessions] == ["after-floor"]


def test_backfill_resumes_after_the_cursor_checkpoint():
    repository = TrackingMessageRepository()
    item = conversation("resume")
    checkpoint = NOW - timedelta(days=3)
    repository.save(message(item.conversation_id, "at-checkpoint", checkpoint))
    repository.save(message(item.conversation_id, "after-checkpoint", checkpoint + timedelta(hours=2)))
    cursor = DreamCursor(
        agent_id=AGENT_ID,
        user_id=OWNER,
        last_session_ended_at=checkpoint,
        backfill_completed=False,
    )

    window = build_window([item], repository, cursor=cursor)

    assert window.mode == "backfill"
    assert window.start == checkpoint
    assert [session.messages[-1].message_id for session in window.sessions] == ["after-checkpoint"]


def test_automation_conversations_are_excluded_before_the_message_probe():
    repository = TrackingMessageRepository()
    automated = AutomationConversation(
        conversation_id="automation",
        title="Automation",
        agent_id=AGENT_ID,
        created_by=OWNER,
        automation_id="automation-1",
        automation_run_id="run-1",
        created_at=NOW - timedelta(days=2),
    )
    repository.save(message(automated.conversation_id, "automation-message", NOW - timedelta(days=1)))

    window = build_window([automated], repository)

    assert window.sessions == []
    assert repository.probed_conversation_ids == []
    assert repository.paged_conversation_ids == []


def test_sessions_are_chronological_across_conversations_after_paged_reads():
    repository = TrackingMessageRepository()
    later = conversation("later")
    earlier = conversation("earlier")
    repository.save(message(later.conversation_id, "later-message", NOW - timedelta(hours=4)))
    repository.save(message(earlier.conversation_id, "earlier-message", NOW - timedelta(hours=6)))

    window = build_window([later, earlier], repository)

    assert [session.conversation_id for session in window.sessions] == ["earlier", "later"]
    assert repository.paged_conversation_ids == ["later", "earlier"]
