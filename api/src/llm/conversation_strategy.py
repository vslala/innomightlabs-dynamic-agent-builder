"""
Conversation context building strategies.

These strategies determine how conversation history is prepared for LLM input,
managing context window limits and message selection.

Note: Strategies only handle conversation messages. The agent architecture
is responsible for adding system prompts, memory blocks, tools, etc.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.messages.models import Message


class ConversationStrategy(ABC):
    """
    Abstract base class for conversation context building strategies.

    Strategies control how conversation history is prepared for the LLM,
    handling token/word limits and message prioritization.

    Note: Strategies only return conversation messages (user/assistant).
    The agent architecture is responsible for prepending system prompts,
    memory blocks, and other context elements.
    """

    @abstractmethod
    def build_context(
        self,
        messages: list["Message"],
        session_timeout_minutes: int = 0,
    ) -> list[dict]:
        """
        Build message context from conversation history.

        Args:
            messages: List of messages in the conversation (chronological order)
            session_timeout_minutes: If > 0, return empty context if the gap between
                                     now and last message exceeds this timeout.
                                     0 = no timeout (load all messages within word limit)

        Returns:
            List of dicts with 'role' and 'content' keys (user/assistant only)
        """
        pass


class FixedWindowStrategy(ConversationStrategy):
    """
    Fixed window strategy that keeps messages within a word limit.

    This strategy:
    1. Includes as many recent messages as possible within the word limit
    2. Drops older messages when the limit is exceeded
    """

    def __init__(self, max_words: int = 10000):
        """
        Initialize the fixed window strategy.

        Args:
            max_words: Maximum number of words to include in context
        """
        self.max_words = max_words

    def build_context(
        self,
        messages: list["Message"],
        session_timeout_minutes: int = 0,
    ) -> list[dict]:
        """
        Build context keeping the most recent messages within word limit.

        The strategy works backwards from the most recent message,
        including messages until the word limit is reached.

        If session_timeout_minutes > 0 and the gap between now and the last
        message exceeds the timeout, returns an empty context (fresh start).

        Args:
            messages: List of messages sorted by created_at ascending
            session_timeout_minutes: Session timeout in minutes (0 = no timeout)

        Returns:
            List of message dicts (user/assistant only, no system prompt)
        """
        if not messages:
            return []

        # Check if session has expired (gap between now and last message)
        if session_timeout_minutes > 0:
            last_message = messages[-1]
            now = datetime.now(timezone.utc)
            gap_seconds = (now - last_message.created_at).total_seconds()
            gap_minutes = gap_seconds / 60

            if gap_minutes > session_timeout_minutes:
                # Session expired - return empty context (fresh start)
                # The LLM can use recall_conversation tool to access older messages
                return []

        # Work backwards from newest messages
        word_count = 0
        selected_messages: list["Message"] = []

        for msg in reversed(messages):
            msg_words = len(msg.content.split())

            # Check if adding this message would exceed the limit
            if word_count + msg_words > self.max_words:
                break

            # Insert at beginning to maintain chronological order
            selected_messages.insert(0, msg)
            word_count += msg_words

        # Convert to dict format with attachment formatting
        return [
            {"role": msg.role, "content": self._format_with_attachments(msg)}
            for msg in selected_messages
        ]

    def _format_with_attachments(self, msg: "Message") -> str:
        """Format message content with attachments for LLM context."""
        if not msg.attachments:
            return msg.content

        attachment_sections = []
        for att in msg.attachments:
            attachment_sections.append(
                f'<attached_file name="{att.filename}">\n{att.content}\n</attached_file>'
            )

        attachments_text = "\n\n".join(attachment_sections)
        return f"{attachments_text}\n\n{msg.content}"

    def __repr__(self) -> str:
        return f"FixedWindowStrategy(max_words={self.max_words})"
