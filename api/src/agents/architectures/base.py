"""
Base Agent Architecture interface.

Agent architectures are responsible for the end-to-end workflow of handling
a user message, including:
- Building context (conversation history, memory blocks, tools, etc.)
- Calling the LLM provider
- Deciding whether to loop or return the response
- Emitting SSE events throughout the lifecycle
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, AsyncIterator

if TYPE_CHECKING:
    from src.agents.models import Agent
    from src.conversations.models import Conversation
    from src.llm.events import SSEEvent


class AgentArchitecture(ABC):
    """
    Abstract base class for agent architectures.

    Each architecture implements a different approach to handling conversations:
    - krishna-mini: Simple conversation with fixed context window
    - krishna-memgpt: Memory-augmented architecture with working memory, reflection, etc.
    """

    @abstractmethod
    async def handle_message(
        self,
        agent: "Agent",
        conversation: "Conversation",
        user_message: str,
    ) -> AsyncIterator["SSEEvent"]:
        """
        Handle a user message and stream SSE events.

        This method is responsible for the full lifecycle:
        1. Save the user message
        2. Build context (conversation + memory + tools as needed)
        3. Call the LLM provider
        4. Decide whether to loop or return
        5. Save the assistant message
        6. Emit appropriate SSE events throughout

        Args:
            agent: The agent handling this conversation
            conversation: The conversation context
            user_message: The user's message content

        Yields:
            SSEEvent objects for streaming to the client
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the architecture name (e.g., 'krishna-mini')."""
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
