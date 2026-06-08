from __future__ import annotations

from typing import Optional, Tuple

from src.messages.models import Message
from src.messages.repositories.compaction import (
    MessageCompactionStrategy,
    TemplateMessageCompactionStrategy,
)


class InMemoryMessageRepository:
    context_token_limit: int = 150_000
    compaction_target_ratio: float = 0.30
    chars_per_token: int = 4

    def __init__(self, compaction_strategy: MessageCompactionStrategy | None = None):
        self._messages: list[Message] = []
        self.compaction_strategy = compaction_strategy or TemplateMessageCompactionStrategy(
            chars_per_token=self.chars_per_token,
        )

    def save(self, message: Message) -> Message:
        self._messages.append(message)
        self._compact_if_needed(message.conversation_id)
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

    def _compact_if_needed(self, conversation_id: str) -> None:
        messages = [
            message
            for message in self._messages
            if message.conversation_id == conversation_id
        ]
        messages.sort(key=lambda item: item.created_at)
        if not messages:
            return

        estimated_tokens = self._estimate_tokens(messages)
        if estimated_tokens <= self.context_token_limit:
            return

        compacted = self.compaction_strategy.compact(
            conversation_id=conversation_id,
            messages=messages,
            target_tokens=int(self.context_token_limit * self.compaction_target_ratio),
        )
        self._replace_conversation_messages(conversation_id, compacted)

    def _estimate_tokens(self, messages: list[Message]) -> int:
        total_chars = 0
        for message in messages:
            total_chars += len(message.content)
            for attachment in message.attachments:
                total_chars += len(attachment.content)
        return total_chars // self.chars_per_token

    def _replace_conversation_messages(self, conversation_id: str, compacted: Message) -> None:
        self._messages = [
            message
            for message in self._messages
            if message.conversation_id != conversation_id
        ]
        self._messages.append(compacted)
