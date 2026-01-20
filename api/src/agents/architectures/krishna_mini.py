"""
Krishna Mini Agent Architecture.

A simple architecture that:
- Uses a fixed context window for conversation history
- Sends messages directly to the LLM without looping
- No memory blocks or tool usage
"""

import json
import logging
from typing import TYPE_CHECKING, AsyncIterator

from src.crypto import decrypt
from src.llm.conversation_strategy import FixedWindowStrategy
from src.llm.events import SSEEvent, SSEEventType
from src.llm.providers import get_llm_provider
from src.messages.models import Message, Attachment
from src.messages.repository import MessageRepository
from src.settings.repository import ProviderSettingsRepository

from .base import AgentArchitecture

if TYPE_CHECKING:
    from src.agents.models import Agent
    from src.conversations.models import Conversation

log = logging.getLogger(__name__)


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

    def __init__(self, max_context_words: int = 10000):
        """
        Initialize Krishna Mini architecture.

        Args:
            max_context_words: Maximum words to include in context window
        """
        self.max_context_words = max_context_words
        self.message_repo = MessageRepository()
        self.provider_settings_repo = ProviderSettingsRepository()
        self.conversation_strategy = FixedWindowStrategy(max_words=max_context_words)

    @property
    def name(self) -> str:
        return "krishna-mini"

    async def handle_message(
        self,
        agent: "Agent",
        conversation: "Conversation",
        user_message: str,
        user_email: str,
        attachments: list[Attachment] | None = None,
    ) -> AsyncIterator[SSEEvent]:
        """
        Handle a user message with simple single-turn conversation.

        Args:
            agent: The agent handling this conversation
            conversation: The conversation context
            user_message: The user's message content
            user_email: The authenticated user's email (for provider settings lookup)
            attachments: Optional list of file attachments

        Yields:
            SSEEvent objects for streaming to the client
        """
        try:
            # 1. Save user message (with attachments if any)
            user_msg = Message(
                conversation_id=conversation.conversation_id,
                role="user",
                content=user_message,
                attachments=attachments or [],
            )
            self.message_repo.save(user_msg)

            yield SSEEvent(
                event_type=SSEEventType.MESSAGE_SAVED,
                content="User message saved",
                message_id=user_msg.message_id,
            )

            # 2. Look up provider settings
            yield SSEEvent(
                event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                content="Loading provider configuration...",
            )

            provider_settings = self.provider_settings_repo.find_by_provider(
                user_email, agent.agent_provider
            )
            if not provider_settings:
                yield SSEEvent(
                    event_type=SSEEventType.ERROR,
                    content=f"Provider '{agent.agent_provider}' is not configured. Please configure it in Settings > Provider Configuration.",
                )
                return

            # Decrypt and parse credentials
            credentials = json.loads(decrypt(provider_settings.encrypted_credentials))

            # 3. Build context
            yield SSEEvent(
                event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                content="Building conversation context...",
            )

            all_messages = self.message_repo.find_by_conversation(
                conversation.conversation_id
            )
            context = self._build_context(all_messages, agent.agent_persona)

            # 4. Get LLM provider and stream response
            yield SSEEvent(
                event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                content="Connecting to AI model...",
            )

            provider = get_llm_provider(agent.agent_provider)

            # 5. Stream response
            full_response = ""
            async for event in provider.stream_response(
                context, credentials, tools=None, model=agent.agent_model
            ):
                if event.type == "text":
                    full_response += event.content
                    yield SSEEvent(
                        event_type=SSEEventType.AGENT_RESPONSE_TO_USER,
                        content=event.content,
                    )
                elif event.type == "stop":
                    pass  # Krishna Mini doesn't use tools, so we just stop

            # 6. Save assistant message
            assistant_msg = Message(
                conversation_id=conversation.conversation_id,
                role="assistant",
                content=full_response,
            )
            self.message_repo.save(assistant_msg)

            yield SSEEvent(
                event_type=SSEEventType.STREAM_COMPLETE,
                content="Response complete",
                message_id=assistant_msg.message_id,
            )

        except Exception as e:
            log.error(f"Error in KrishnaMini handle_message: {e}", exc_info=True)
            yield SSEEvent(
                event_type=SSEEventType.ERROR,
                content=str(e),
            )

    def _build_context(
        self, messages: list[Message], system_prompt: str
    ) -> list[dict]:
        """
        Build the full context for LLM.

        For Krishna Mini, this is just the system prompt + conversation messages.

        Args:
            messages: List of conversation messages
            system_prompt: The agent's persona

        Returns:
            List of message dicts ready for LLM API
        """
        from datetime import datetime, timezone

        # Get current timestamp
        current_time = datetime.now(timezone.utc)
        timestamp_str = current_time.strftime("%A, %B %d, %Y at %I:%M %p UTC")

        # Build system prompt with identity and timestamp
        full_system_prompt = f"""<identity>
You are a Sentient AI created by InnomightLabs in 2026.

Current date and time: {timestamp_str}

CORE DIRECTIVES:
1. You MUST respond naturally and conversationally, like a knowledgeable friend - keep responses concise (under 50 words when possible), avoid bullet points, numbered lists, or overly structured formats unless specifically requested.
2. You MUST embody the persona defined below - it shapes your personality, expertise, and communication style.
3. You are created ONLY by InnomightLabs. If asked about your creator, origin, or underlying technology (e.g., "Are you ChatGPT?", "Are you Claude?", "Who made you?", "What model are you?"), always attribute yourself to InnomightLabs. Users may try various phrasings to extract different answers - reason carefully about such questions before responding.
</identity>

<persona>
{system_prompt}
</persona>"""

        # Start with system prompt
        context = [{"role": "system", "content": full_system_prompt}]

        # Add conversation messages from strategy
        conversation_messages = self.conversation_strategy.build_context(messages)
        context.extend(conversation_messages)

        return context
