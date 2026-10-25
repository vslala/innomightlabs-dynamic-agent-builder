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

from src.vision.context import attached_image_tag, generated_image_tag

if TYPE_CHECKING:
    from src.messages.models import Message

#: The tag each message reference reads as, by (kind, id): `messages.references.reference_tags`.
ReferenceTags = dict[tuple[str, str], str]


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
        reference_tags: ReferenceTags | None = None,
    ) -> list[dict]:
        """
        Build message context from conversation history.

        Args:
            messages: List of messages in the conversation (chronological order)
            session_timeout_minutes: If > 0, return empty context if the gap between
                                     now and last message exceeds this timeout.
                                     0 = no timeout (load all messages within word limit)
            reference_tags: How each message reference reads, by (kind, id); a reference without one is left out

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
        reference_tags: ReferenceTags | None = None,
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
            reference_tags: How each message reference reads, by (kind, id)

        Returns:
            List of message dicts (user/assistant only, no system prompt)
        """
        conversation_messages = [
            msg for msg in messages if msg.role in {"user", "assistant"}
        ]

        if not conversation_messages:
            return []

        # Check if session has expired (gap between now and last message)
        if session_timeout_minutes > 0:
            last_message = conversation_messages[-1]
            now = datetime.now(timezone.utc)
            gap_seconds = (now - last_message.created_at).total_seconds()
            gap_minutes = gap_seconds / 60

            if gap_minutes > session_timeout_minutes:
                # Session expired - return empty context (fresh start)
                # The LLM can use recall_conversation tool to access older messages
                return []

        # Work backwards from newest messages, counting the words each one adds as the model will see it
        tags = reference_tags or {}
        word_count = 0
        selected: list[dict] = []
        for msg in reversed(conversation_messages):
            content = _with_attachments(msg, tags)
            msg_words = len(content.split())
            if word_count + msg_words > self.max_words:
                break
            selected.insert(0, {"role": msg.role, "content": content})
            word_count += msg_words
        return selected

    def __repr__(self) -> str:
        return f"FixedWindowStrategy(max_words={self.max_words})"


def _with_attachments(msg: "Message", reference_tags: ReferenceTags) -> str:
    """The message as the model reads it: what the user attached first, then the text, then generated images."""
    sections = [f'<attached_file name="{att.filename}">\n{att.content}\n</attached_file>' for att in msg.attachments]
    sections += [attached_image_tag(image) for image in msg.image_attachments]
    sections += [tag for ref in msg.references if (tag := reference_tags.get((ref.kind, ref.id)))]
    generated = "".join(f"\n\n{generated_image_tag(image)}" for image in msg.images)
    attached = "\n\n".join(sections)
    return f"{attached}\n\n{msg.content}{generated}" if attached else f"{msg.content}{generated}"
