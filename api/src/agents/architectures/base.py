"""
Base Agent Architecture interface.

Agent architectures are responsible for the end-to-end workflow of handling
a user message, including:
- Building context (conversation history, memory blocks, tools, etc.)
- Calling the LLM provider
- Deciding whether to loop or return the response
- Emitting SSE events throughout the lifecycle
"""

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, AsyncIterator

from pydantic import BaseModel, Field

from src.exceptions import client_error_message
from src.skills.models import ActorKind
from src.llm.events import SSEEvent, SSEEventType

log = logging.getLogger(__name__)


def turn_error_message(exc: Exception, actor_kind: ActorKind) -> str:
    """The owner sees what went wrong with their own agent (a provider rejecting their key, say).
    Everyone else sees only that it failed, unless the error was written for them."""
    return str(exc) if actor_kind == ActorKind.OWNER else client_error_message(exc)

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

    def add(self, event: SSEEvent) -> None:
        """Fold one streamed event into the buffered result."""
        self.events.append(event)

        if event.event_type == SSEEventType.AGENT_RESPONSE_TO_USER:
            self.response_text += event.content
        elif event.event_type == SSEEventType.USER_MESSAGE_SAVED:
            self.user_message_id = event.message_id
        elif event.event_type == SSEEventType.ASSISTANT_MESSAGE_SAVED:
            self.assistant_message_id = event.message_id
        elif event.event_type == SSEEventType.ERROR:
            self.success = False
            self.error = event.content


class AgentArchitecture(ABC):
    """
    Abstract base class for agent architectures.

    Each architecture implements a different approach to handling conversations:
    - krishna-mini: Simple conversation with fixed context window
    - krishna-memgpt: Memory-augmented architecture with working memory, reflection, etc.
    """

    async def handle_message(
        self,
        agent: "Agent",
        conversation: "Conversation",
        user_message: str,
        owner_email: str,
        actor_email: str,
        actor_id: str,
        actor_kind: "ActorKind",
        attachments: list["Attachment"] | None = None,
        api_key_id: str | None = None,
    ) -> AsyncIterator["SSEEvent"]:
        """
        Handle a user message and stream SSE events.

        Runs `_run_turn` and owns the two things every architecture must get
        right identically: any escaping exception becomes a single ERROR event,
        and a turn that did not fail ends with STREAM_COMPLETE.

        Args:
            agent: The agent handling this conversation
            conversation: The conversation context
            user_message: The user's message content
            owner_email: The agent owner's email (tenant context; used for provider settings lookup)
            actor_email: The end-user's email (who is speaking)
            actor_id: The end-user's ID (used for memory scoping)
            actor_kind: Who the end-user is to the agent; decides which tools they get
            attachments: Optional list of file attachments
            api_key_id: The public API secret key the turn runs under, if any (usage attribution)

        Yields:
            SSEEvent objects for streaming to the client
        """
        failed = False
        try:
            async for event in self._run_turn(
                agent=agent,
                conversation=conversation,
                user_message=user_message,
                owner_email=owner_email,
                actor_email=actor_email,
                actor_id=actor_id,
                actor_kind=actor_kind,
                attachments=attachments,
                api_key_id=api_key_id,
            ):
                failed = failed or event.event_type == SSEEventType.ERROR
                yield event
        except Exception as exc:
            log.error("Error in %s turn: %s", self.name, exc, exc_info=True)
            yield SSEEvent(event_type=SSEEventType.ERROR, content=turn_error_message(exc, actor_kind))
            return

        if not failed:
            yield SSEEvent(event_type=SSEEventType.STREAM_COMPLETE, content="Response complete")

    def _run_turn(
        self,
        *,
        agent: "Agent",
        conversation: "Conversation",
        user_message: str,
        owner_email: str,
        actor_email: str,
        actor_id: str,
        actor_kind: "ActorKind",
        attachments: list["Attachment"] | None = None,
        api_key_id: str | None = None,
    ) -> AsyncIterator["SSEEvent"]:
        """Stream one turn's content events. Errors may simply be raised.

        Not abstract: a test double is free to override `handle_message`
        directly when it wants no lifecycle handling at all.
        """
        raise NotImplementedError(f"{type(self).__name__} must implement _run_turn")

    async def handle_message_buffered(
        self,
        agent: "Agent",
        conversation: "Conversation",
        user_message: str,
        owner_email: str,
        actor_email: str,
        actor_id: str,
        actor_kind: "ActorKind",
        attachments: list["Attachment"] | None = None,
        api_key_id: str | None = None,
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
            actor_kind=actor_kind,
            attachments=attachments,
            api_key_id=api_key_id,
        ):
            result.add(event)

        return result

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the architecture name (e.g., 'krishna-mini')."""
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
