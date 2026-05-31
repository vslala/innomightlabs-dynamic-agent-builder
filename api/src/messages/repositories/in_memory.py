from __future__ import annotations

from typing import Optional, Tuple

from src.messages.models import Message


class InMemoryMessageRepository:
    def __init__(self):
        self._messages: list[Message] = []

    def save(self, message: Message) -> Message:
        self._messages.append(message)
        return message

    def find_by_conversation(self, conversation_id: str) -> list[Message]:
        messages = [
            message
            for message in self._messages
            if message.conversation_id == conversation_id
        ]
        messages.sort(key=lambda item: item.created_at)
        return messages

    def find_by_conversation_paginated(
        self,
        conversation_id: str,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Tuple[list[Message], Optional[str], bool]:
        del cursor
        messages = self.find_by_conversation(conversation_id)
        return messages[:limit], None, len(messages) > limit

    def find_by_conversation_newest_first(
        self,
        conversation_id: str,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> Tuple[list[Message], Optional[str], bool]:
        del cursor
        messages = list(reversed(self.find_by_conversation(conversation_id)))
        return messages[:limit], None, len(messages) > limit

    def count_by_conversation(self, conversation_id: str) -> int:
        return len(self.find_by_conversation(conversation_id))

    def delete_by_conversation(self, conversation_id: str) -> int:
        before = len(self._messages)
        self._messages = [
            message
            for message in self._messages
            if message.conversation_id != conversation_id
        ]
        return before - len(self._messages)
