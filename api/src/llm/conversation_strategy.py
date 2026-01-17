"""
Conversation context building strategies.

These strategies determine how conversation history is prepared for LLM input,
managing context window limits and message selection.

Note: Strategies only handle conversation messages. The agent architecture
is responsible for adding system prompts, memory blocks, tools, etc.
"""

from abc import ABC, abstractmethod
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
    def build_context(self, messages: list["Message"]) -> list[dict]:
        """
        Build message context from conversation history.

        Args:
            messages: List of messages in the conversation (chronological order)

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

    def build_context(self, messages: list["Message"]) -> list[dict]:
        """
        Build context keeping the most recent messages within word limit.

        The strategy works backwards from the most recent message,
        including messages until the word limit is reached.

        Args:
            messages: List of messages sorted by created_at ascending

        Returns:
            List of message dicts (user/assistant only, no system prompt)
        """
        if not messages:
            return []

        # Work backwards from newest messages
        word_count = 0
        selected_messages = []

        for msg in reversed(messages):
            msg_words = len(msg.content.split())

            # Check if adding this message would exceed the limit
            if word_count + msg_words > self.max_words:
                break

            # Insert at beginning to maintain chronological order
            selected_messages.insert(0, msg)
            word_count += msg_words

        # Convert to dict format
        return [{"role": msg.role, "content": msg.content} for msg in selected_messages]

    def __repr__(self) -> str:
        return f"FixedWindowStrategy(max_words={self.max_words})"
