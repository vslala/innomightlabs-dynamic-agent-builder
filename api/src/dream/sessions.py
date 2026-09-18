"""Pure session derivation and lossless transcript chunking for Dream."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import NamedTuple

from src.messages.models import Message


@dataclass(frozen=True)
class DreamSession:
    conversation_id: str
    conversation_title: str
    messages: list[Message]

    @property
    def started_at(self) -> datetime:
        return self.messages[0].created_at

    @property
    def ended_at(self) -> datetime:
        return self.messages[-1].created_at


@dataclass(frozen=True)
class DreamSessionChunk:
    session: DreamSession
    index: int
    total: int
    messages: list[Message]
    granularity: str
    window_of_message_id: str = ""
    window_index: int = 0
    window_total: int = 1


class MessageExchange(NamedTuple):
    messages: list[Message]

    @property
    def word_count(self) -> int:
        return sum(_word_count(message) for message in self.messages)


def _word_count(message: Message) -> int:
    return len(message.content.split())


def _messages_word_count(messages: list[Message]) -> int:
    return sum(_word_count(message) for message in messages)


class SessionSegmenter:
    """Split ordered user/assistant traffic at inactivity gaps."""

    def segment(
        self,
        conversation_id: str,
        conversation_title: str,
        messages: list[Message],
        session_timeout_minutes: int,
    ) -> list[DreamSession]:
        assert all(
            earlier.created_at <= later.created_at
            for earlier, later in zip(messages, messages[1:])
        ), "messages must be sorted ascending by created_at"

        relevant = [message for message in messages if message.role in {"user", "assistant"}]
        if not relevant:
            return []
        if session_timeout_minutes <= 0:
            return self._sessions_with_user(conversation_id, conversation_title, [relevant])

        timeout = timedelta(minutes=session_timeout_minutes)
        grouped: list[list[Message]] = [[relevant[0]]]
        for message in relevant[1:]:
            if message.created_at - grouped[-1][-1].created_at > timeout:
                grouped.append([message])
            else:
                grouped[-1].append(message)
        return self._sessions_with_user(conversation_id, conversation_title, grouped)

    @staticmethod
    def _sessions_with_user(
        conversation_id: str, conversation_title: str, grouped: list[list[Message]]
    ) -> list[DreamSession]:
        return [
            DreamSession(conversation_id, conversation_title, messages)
            for messages in grouped
            if any(message.role == "user" for message in messages)
        ]


def split_into_exchanges(messages: list[Message]) -> list[MessageExchange]:
    """Fold ordered messages into user-led exchanges without dropping leading assistants."""
    exchanges: list[list[Message]] = []
    current: list[Message] | None = None
    for message in messages:
        if message.role == "user":
            if current:
                exchanges.append(current)
            current = [message]
        elif current is None:
            current = [message]
        else:
            current.append(message)
    if current:
        exchanges.append(current)
    return [MessageExchange(messages) for messages in exchanges]


class SessionChunker:
    """Recursively subdivide a session without discarding transcript content."""

    def chunk(
        self, session: DreamSession, max_words: int, window_overlap_words: int
    ) -> list[DreamSessionChunk]:
        if max_words <= 0:
            raise ValueError("max_words must be greater than zero")
        if not 0 <= window_overlap_words < max_words:
            raise ValueError("window_overlap_words must be non-negative and smaller than max_words")

        if _messages_word_count(session.messages) <= max_words:
            return self._build_chunks(session, [(session.messages, "session", "", 0, 1)])

        units = self._exchange_groups(split_into_exchanges(session.messages), max_words)
        raw_chunks: list[tuple[list[Message], str, str, int, int]] = []
        for exchange_group in units:
            if exchange_group[0].word_count <= max_words:
                raw_chunks.append((self._flatten(exchange_group), "exchange_group", "", 0, 1))
                continue
            raw_chunks.extend(
                self._chunk_exchange(exchange_group[0], max_words, window_overlap_words)
            )
        return self._build_chunks(session, raw_chunks)

    @staticmethod
    def _exchange_groups(
        exchanges: list[MessageExchange], max_words: int
    ) -> list[list[MessageExchange]]:
        groups: list[list[MessageExchange]] = []
        current: list[MessageExchange] = []
        current_words = 0
        for exchange in exchanges:
            if current and current_words + exchange.word_count > max_words:
                groups.append(current)
                current = []
                current_words = 0
            current.append(exchange)
            current_words += exchange.word_count
        if current:
            groups.append(current)
        return groups

    def _chunk_exchange(
        self, exchange: MessageExchange, max_words: int, overlap: int
    ) -> list[tuple[list[Message], str, str, int, int]]:
        if exchange.word_count <= max_words:
            return [(exchange.messages, "exchange", "", 0, 1)]
        chunks: list[tuple[list[Message], str, str, int, int]] = []
        for message in exchange.messages:
            if _word_count(message) <= max_words:
                chunks.append(([message], "message", "", 0, 1))
            else:
                chunks.extend(self._message_windows(message, max_words, overlap))
        return chunks

    @staticmethod
    def _message_windows(
        message: Message, max_words: int, overlap: int
    ) -> list[tuple[list[Message], str, str, int, int]]:
        words = message.content.split()
        step = max_words - overlap
        starts = list(range(0, len(words), step))
        windows = [words[start : start + max_words] for start in starts]
        total = len(windows)
        return [
            ([message.model_copy(update={"content": " ".join(window)})], "window", message.message_id, index, total)
            for index, window in enumerate(windows)
        ]

    @staticmethod
    def _flatten(exchanges: list[MessageExchange]) -> list[Message]:
        return [message for exchange in exchanges for message in exchange.messages]

    @staticmethod
    def _build_chunks(
        session: DreamSession,
        raw_chunks: list[tuple[list[Message], str, str, int, int]],
    ) -> list[DreamSessionChunk]:
        total = len(raw_chunks)
        return [
            DreamSessionChunk(session, index, total, messages, granularity, message_id, window_index, window_total)
            for index, (messages, granularity, message_id, window_index, window_total) in enumerate(raw_chunks)
        ]
