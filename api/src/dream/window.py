"""Select closed, unprocessed conversation sessions for a Dream run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from src.conversations.models import AutomationConversation
from src.conversations.repository import ConversationRepository
from src.dream.models import DreamCursor, DreamSettings
from src.dream.sessions import DreamSession, SessionSegmenter
from src.messages.repositories.base import MessageRepository


@dataclass(frozen=True)
class DreamWindow:
    mode: Literal["backfill", "daily", "manual"]
    start: datetime
    end: datetime
    sessions: list[DreamSession]
    truncated: bool = False


class DreamWindowBuilder:
    def __init__(
        self,
        *,
        conversation_repository: ConversationRepository,
        message_repository: MessageRepository,
        segmenter: SessionSegmenter | None = None,
        page_size: int = 200,
    ) -> None:
        self.conversation_repository = conversation_repository
        self.message_repository = message_repository
        self.segmenter = segmenter or SessionSegmenter()
        self.page_size = page_size

    def build(
        self,
        *,
        agent_id: str,
        owner_email: str,
        session_timeout_minutes: int,
        settings: DreamSettings,
        cursor: DreamCursor | None,
        now: datetime | None = None,
        requested_mode: Literal["backfill", "daily", "manual"] = "daily",
    ) -> DreamWindow:
        now = now or datetime.now(timezone.utc)
        mode: Literal["backfill", "daily", "manual"]
        if requested_mode == "manual":
            mode = "manual"
        elif cursor is None or not cursor.backfill_completed:
            mode = "backfill"
        else:
            mode = "daily"

        floor = now - timedelta(days=settings.backfill_days)
        if mode in {"backfill", "manual"}:
            cursor_start = cursor.last_session_ended_at if cursor else None
            start = max(cursor_start or datetime.min.replace(tzinfo=timezone.utc), floor)
        else:
            assert cursor is not None and cursor.last_session_ended_at is not None
            start = cursor.last_session_ended_at
        end = now - timedelta(minutes=max(session_timeout_minutes, 0))
        sessions: list[DreamSession] = []
        for conversation in self.conversation_repository.find_all_by_user(owner_email):
            if conversation.agent_id != agent_id or isinstance(conversation, AutomationConversation):
                continue
            if not self.message_repository.has_messages_after(conversation.conversation_id, start):
                continue
            messages = self._messages(conversation.conversation_id)
            sessions.extend(
                session
                for session in self.segmenter.segment(
                    conversation.conversation_id,
                    conversation.title,
                    messages,
                    session_timeout_minutes,
                )
                if start < session.ended_at <= end
            )
        sessions.sort(key=lambda session: (session.started_at, session.conversation_id))
        return DreamWindow(mode=mode, start=start, end=end, sessions=sessions)

    def _messages(self, conversation_id: str) -> list:
        messages = []
        cursor = None
        while True:
            page, cursor, has_more = self.message_repository.find_by_conversation_paginated(
                conversation_id, limit=self.page_size, cursor=cursor
            )
            messages.extend(page)
            if not has_more:
                return messages
