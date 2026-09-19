"""
Krishna Mini Agent Architecture.

A simple architecture that:
- Uses a fixed context window for conversation history
- Sends messages directly to the LLM without looping
- No memory blocks or tool usage
"""

import logging
from typing import TYPE_CHECKING, AsyncIterator

from src.agents.prompts import render_system_prompt
from src.agents.provider_session import open_provider_session
from src.llm.conversation_strategy import FixedWindowStrategy
from src.llm.events import SSEEvent, SSEEventType
from src.messages.models import Message, Attachment
from src.messages.repositories import MessageRepository, get_message_repository
from src.settings.repository import get_provider_settings_repository

from .base import AgentArchitecture

if TYPE_CHECKING:
    from src.agents.models import Agent
    from src.conversations.models import Conversation

log = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = "krishna_mini_system_prompt.j2"


class KrishnaMiniArchitecture(AgentArchitecture):
    """
    Krishna Mini - A simple conversational agent architecture.

    This architecture:
    1. Saves user messages to the conversation
    2. Builds context using FixedWindowStrategy (10,000 word limit)
    3. Calls the LLM once and streams the response
    4. Saves the assistant response

    No looping, memory, or tool usage - just straightforward conversation.
    """

    def __init__(
        self,
        max_context_words: int = 10000,
        *,
        message_repository: MessageRepository | None = None,
    ):
        self.message_repo = message_repository or get_message_repository("dynamodb")
        self.provider_settings_repo = get_provider_settings_repository()
        self.conversation_strategy = FixedWindowStrategy(max_words=max_context_words)

    @property
    def name(self) -> str:
        return "krishna-mini"

    async def _run_turn(
        self,
        *,
        agent: "Agent",
        conversation: "Conversation",
        user_message: str,
        owner_email: str,
        actor_email: str,
        actor_id: str,
        attachments: list[Attachment] | None = None,
    ) -> AsyncIterator[SSEEvent]:
        """One LLM call, streamed. `actor_id` is unused: Krishna Mini has no memory."""
        user_msg = Message(
            conversation_id=conversation.conversation_id,
            created_by=actor_email,
            role="user",
            content=user_message,
            attachments=attachments or [],
        )
        self.message_repo.save(user_msg)
        yield SSEEvent(
            event_type=SSEEventType.USER_MESSAGE_SAVED,
            content="User message saved",
            message_id=user_msg.message_id,
        )

        yield SSEEvent(
            event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
            content="Loading provider configuration...",
        )
        session = await open_provider_session(
            agent,
            owner_email=owner_email,
            provider_settings_repo=self.provider_settings_repo,
        )

        yield SSEEvent(
            event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
            content="Building conversation context...",
        )
        context = self._build_context(
            self.message_repo.find_by_conversation(conversation.conversation_id),
            agent.agent_persona,
        )

        yield SSEEvent(
            event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
            content="Connecting to AI model...",
        )

        full_response = ""
        async for event in session.provider.stream_response(
            context, session.credentials, tools=None, model=agent.agent_model
        ):
            if event.type == "text":
                full_response += event.content
                yield SSEEvent(
                    event_type=SSEEventType.AGENT_RESPONSE_TO_USER,
                    content=event.content,
                )

        assistant_msg = Message(
            conversation_id=conversation.conversation_id,
            created_by=actor_email,
            role="assistant",
            content=full_response,
        )
        self.message_repo.save(assistant_msg)
        yield SSEEvent(
            event_type=SSEEventType.ASSISTANT_MESSAGE_SAVED,
            content="Assistant message saved",
            message_id=assistant_msg.message_id,
        )

    def _build_context(self, messages: list[Message], agent_persona: str) -> list[dict]:
        """System prompt followed by the conversation window."""
        return [
            {
                "role": "system",
                "content": render_system_prompt(
                    SYSTEM_PROMPT_TEMPLATE,
                    has_memory_tools=False,
                    agent_persona=agent_persona,
                ),
            },
            *self.conversation_strategy.build_context(messages),
        ]
