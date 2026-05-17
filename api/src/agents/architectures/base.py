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

from pydantic import BaseModel, Field

from src.llm.events import SSEEvent, SSEEventType

if TYPE_CHECKING:
    from src.agents.models import Agent
    from src.conversations.models import Conversation
    from src.messages.models import Attachment


class AgentInvocationResult(BaseModel):
    """Buffered result for non-streaming agent invocation."""

    events: list[SSEEvent] = Field(default_factory=list)
    response_text: str = ""
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    success: bool = True
    error: str | None = None


class AgentArchitecture(ABC):
    """
    Abstract base class for agent architectures.

    Each architecture implements a different approach to handling conversations:
    - krishna-mini: Simple conversation with fixed context window
    - krishna-memgpt: Memory-augmented architecture with working memory, reflection, etc.
    """

    @abstractmethod
    def handle_message(
        self,
        agent: "Agent",
        conversation: "Conversation",
        user_message: str,
        owner_email: str,
        actor_email: str,
        actor_id: str,
        attachments: list["Attachment"] | None = None,
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
            owner_email: The agent owner's email (tenant context; used for provider settings lookup)
            actor_email: The end-user's email (who is speaking)
            actor_id: The end-user's ID (used for memory scoping)
            attachments: Optional list of file attachments

        Yields:
            SSEEvent objects for streaming to the client
        """
        pass

    async def handle_message_buffered(
        self,
        agent: "Agent",
        conversation: "Conversation",
        user_message: str,
        owner_email: str,
        actor_email: str,
        actor_id: str,
        attachments: list["Attachment"] | None = None,
    ) -> AgentInvocationResult:
        """
        Handle a user message and return a buffered invocation result.

        This is intended for non-streaming callers such as automations. The default
        implementation consumes the streaming contract and preserves the full event
        timeline while extracting commonly needed message IDs and response text.
        """
        result = AgentInvocationResult()

        async for event in self.handle_message(
            agent=agent,
            conversation=conversation,
            user_message=user_message,
            owner_email=owner_email,
            actor_email=actor_email,
            actor_id=actor_id,
            attachments=attachments,
        ):
            result.events.append(event)

            if event.event_type == SSEEventType.AGENT_RESPONSE_TO_USER:
                result.response_text += event.content
            elif event.event_type == SSEEventType.USER_MESSAGE_SAVED:
                result.user_message_id = event.message_id
            elif event.event_type == SSEEventType.ASSISTANT_MESSAGE_SAVED:
                result.assistant_message_id = event.message_id
            elif event.event_type == SSEEventType.ERROR:
                result.success = False
                result.error = event.content

        return result

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the architecture name (e.g., 'krishna-mini')."""
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
