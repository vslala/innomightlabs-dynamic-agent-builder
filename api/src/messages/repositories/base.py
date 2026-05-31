from __future__ import annotations

from typing import Optional, Protocol, Tuple

from src.messages.models import Message


class MessageRepository(Protocol):
    def save(self, message: Message) -> Message:
        ...

    def find_by_conversation(self, conversation_id: str) -> list[Message]:
        ...

    def find_by_conversation_paginated(
        self,
        conversation_id: str,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Tuple[list[Message], Optional[str], bool]:
        ...

    def find_by_conversation_newest_first(
        self,
        conversation_id: str,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> Tuple[list[Message], Optional[str], bool]:
        ...

    def count_by_conversation(self, conversation_id: str) -> int:
        ...

    def delete_by_conversation(self, conversation_id: str) -> int:
        ...
