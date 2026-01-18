"""
Krishna MemGPT Agent Architecture.

An architecture with memory capabilities:
- Core memory (human/persona) loaded into context every turn
- Archival memory for long-term storage
- Native memory tools for read/write operations
- Agentic loop for tool execution
"""

import json
import logging
from typing import TYPE_CHECKING, AsyncIterator

from src.crypto import decrypt
from src.llm.conversation_strategy import FixedWindowStrategy
from src.llm.events import SSEEvent, SSEEventType
from src.llm.providers import get_llm_provider
from src.memory import MemoryRepository, CoreMemory
from src.messages.models import Message
from src.messages.repository import MessageRepository
from src.settings.repository import ProviderSettingsRepository
from src.tools.native import NATIVE_TOOLS, NativeToolHandler

from .base import AgentArchitecture

if TYPE_CHECKING:
    from src.agents.models import Agent
    from src.conversations.models import Conversation

log = logging.getLogger(__name__)


class KrishnaMemGPTArchitecture(AgentArchitecture):
    """
    Krishna MemGPT - An agent architecture with memory capabilities.

    This architecture:
    1. Initializes default memory blocks (human/persona) on first use
    2. Loads core memory into the system prompt every turn
    3. Provides native memory tools to the LLM
    4. Runs an agentic loop to handle tool calls
    5. Tracks capacity warnings and handles auto-compaction

    Memory blocks are persisted in DynamoDB and survive across conversations.
    """

    MAX_TOOL_ITERATIONS = 10  
    CAPACITY_WARNING_THRESHOLD = 0.80 

    def __init__(self, max_context_words: int = 8000):
        """
        Initialize Krishna MemGPT architecture.

        Args:
            max_context_words: Maximum words to include in conversation context
        """
        self.max_context_words = max_context_words
        self.message_repo = MessageRepository()
        self.memory_repo = MemoryRepository()
        self.provider_settings_repo = ProviderSettingsRepository()
        self.tool_handler = NativeToolHandler(self.memory_repo)
        self.conversation_strategy = FixedWindowStrategy(max_words=max_context_words)

    @property
    def name(self) -> str:
        return "krishna-memgpt"

    async def handle_message( # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        agent: "Agent",
        conversation: "Conversation",
        user_message: str,
        user_email: str,
    ) -> AsyncIterator[SSEEvent]:
        """
        Handle a user message with memory-augmented conversation.

        Args:
            agent: The agent handling this conversation
            conversation: The conversation context
            user_message: The user's message content
            user_email: The authenticated user's email

        Yields:
            SSEEvent objects for streaming to the client
        """
        try:
            # 1. Ensure memory blocks are initialized
            self._ensure_memory_initialized(agent.agent_id)

            # 2. Save user message
            user_msg = Message(
                conversation_id=conversation.conversation_id,
                role="user",
                content=user_message,
            )
            self.message_repo.save(user_msg)

            yield SSEEvent(
                event_type=SSEEventType.MESSAGE_SAVED,
                content="User message saved",
                message_id=user_msg.message_id,
            )

            # 3. Look up provider settings
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
                    content=f"Provider '{agent.agent_provider}' is not configured. "
                            "Please configure it in Settings > Provider Configuration.",
                )
                return

            credentials = json.loads(decrypt(provider_settings.encrypted_credentials))

            # 4. Load core memory and build system prompt
            yield SSEEvent(
                event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                content="Loading memory...",
            )

            system_prompt = self._build_system_prompt(agent)

            # Check for capacity warnings
            capacity_warnings = self._check_capacity_warnings(agent.agent_id)
            if capacity_warnings:
                warning_msg = self._build_warning_message(capacity_warnings)
                system_prompt += "\n\n" + warning_msg

            # 5. Build conversation context
            yield SSEEvent(
                event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                content="Building conversation context...",
            )

            all_messages = self.message_repo.find_by_conversation(
                conversation.conversation_id
            )
            context = [{"role": "system", "content": system_prompt}]
            context.extend(self.conversation_strategy.build_context(all_messages))

            # 6. Get LLM provider
            yield SSEEvent(
                event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                content="Connecting to AI model...",
            )

            provider = get_llm_provider(agent.agent_provider)

            # 7. Agentic loop with tool execution
            full_response = ""
            for iteration in range(self.MAX_TOOL_ITERATIONS):
                has_tool_calls = False
                pending_tool_calls = []
                iteration_text = ""  # Text generated in this iteration

                async for event in provider.stream_response(
                    context, credentials, NATIVE_TOOLS, agent.agent_model
                ):
                    if event.type == "text":
                        full_response += event.content
                        iteration_text += event.content
                        yield SSEEvent(
                            event_type=SSEEventType.AGENT_RESPONSE_TO_USER,
                            content=event.content,
                        )

                    elif event.type == "tool_use":
                        has_tool_calls = True
                        pending_tool_calls.append(event)

                        # Emit tool start event for UI timeline
                        yield SSEEvent(
                            event_type=SSEEventType.TOOL_CALL_START,
                            content=f"Calling {event.tool_name}...",
                            tool_name=event.tool_name,
                            tool_args=event.tool_input,
                        )

                    elif event.type == "stop":
                        pass

                # Process all tool calls from this iteration
                if pending_tool_calls:
                    # Add assistant's response to context (text + tool use)
                    # This ensures the LLM knows what it already said when continuing
                    assistant_content = []

                    # Include any text generated before tool calls
                    if iteration_text.strip():
                        assistant_content.append({"text": iteration_text})

                    # Add tool use blocks
                    for tool_event in pending_tool_calls:
                        assistant_content.append({
                            "toolUse": {
                                "toolUseId": tool_event.tool_use_id,
                                "name": tool_event.tool_name,
                                "input": tool_event.tool_input,
                            }
                        })

                    context.append({
                        "role": "assistant",
                        "content": assistant_content,
                    })

                    # Execute tools and collect results
                    tool_results = []
                    for tool_event in pending_tool_calls:
                        try:
                            result = await self.tool_handler.execute(
                                tool_event.tool_name,
                                tool_event.tool_input,
                                agent.agent_id,
                            )
                            success = True
                        except Exception as e:
                            result = f"Error: {str(e)}"
                            success = False
                            log.error(f"Tool execution error: {e}", exc_info=True)

                        # Emit tool result event for UI timeline
                        yield SSEEvent(
                            event_type=SSEEventType.TOOL_CALL_RESULT,
                            content=result[:200] + "..." if len(result) > 200 else result,
                            tool_name=tool_event.tool_name,
                            success=success,
                        )

                        tool_results.append({
                            "toolResult": {
                                "toolUseId": tool_event.tool_use_id,
                                "content": [{"text": result}],
                            }
                        })

                    # Add tool results to context
                    context.append({
                        "role": "user",
                        "content": tool_results,
                    })

                if not has_tool_calls:
                    break

            # 8. Save assistant message (text response only)
            if full_response.strip():
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
            else:
                yield SSEEvent(
                    event_type=SSEEventType.STREAM_COMPLETE,
                    content="Response complete (tools only)",
                )

        except Exception as e:
            log.error(f"Error in KrishnaMemGPT handle_message: {e}", exc_info=True)
            yield SSEEvent(
                event_type=SSEEventType.ERROR,
                content=str(e),
            )

    def _ensure_memory_initialized(self, agent_id: str) -> None:
        """Ensure default memory blocks exist for this agent."""
        block_defs = self.memory_repo.get_block_definitions(agent_id)
        if not block_defs:
            self.memory_repo.initialize_default_blocks(agent_id)
            log.info(f"Initialized default memory blocks for agent {agent_id}")

    def _build_system_prompt(self, agent: "Agent") -> str:
        """
        Build system prompt with core memory included.

        Args:
            agent: The agent

        Returns:
            System prompt string with memory blocks
        """
        # Get all block definitions and their content
        block_defs = self.memory_repo.get_block_definitions(agent.agent_id)
        memories = {
            m.block_name: m
            for m in self.memory_repo.get_all_core_memories(agent.agent_id)
        }

        # Build memory sections
        memory_sections = []
        for block_def in block_defs:
            memory = memories.get(block_def.block_name)
            if memory and memory.lines:
                lines_str = "\n".join(
                    f"{i+1}: {line}" for i, line in enumerate(memory.lines)
                )
                capacity_pct = memory.get_capacity_percent(block_def.word_limit)
                warning = " ⚠️ NEARING CAPACITY" if capacity_pct >= 80 else ""
                memory_sections.append(
                    f"[{block_def.block_name.title()} - {block_def.description}]"
                    f" ({memory.word_count}/{block_def.word_limit} words){warning}\n{lines_str}"
                )
            else:
                memory_sections.append(
                    f"[{block_def.block_name.title()} - {block_def.description}]\n(empty)"
                )

        memory_content = "\n\n".join(memory_sections)

        return f"""{agent.agent_persona}

<core_memory>
{memory_content}
</core_memory>

You have access to memory tools. Use them to:
- Remember new information about the human (core_memory_append to "human")
- Update outdated information (core_memory_replace with line number)
- Remove obsolete facts (core_memory_delete with line number)
- Store detailed information for later (archival_memory_insert)
- Recall past information (archival_memory_search)
- See all available memory blocks (core_memory_list_blocks)

IMPORTANT:
- Block names are LOWERCASE with underscores (e.g., "human", "persona", "important_financial_data")
- Do NOT use title case or descriptions in block names - just the simple name like "human" not "Human - Facts about the user"
- Use core_memory_list_blocks if unsure what blocks are available
- Always use core_memory_read BEFORE modifying a block to get current line numbers
- Core memory is for key facts; use archival for detailed information
- Keep each line concise and factual"""

    def _check_capacity_warnings(self, agent_id: str) -> list[dict]:
        """Check for memory blocks at or above warning threshold."""
        block_defs = self.memory_repo.get_block_definitions(agent_id)
        memories = {
            m.block_name: m
            for m in self.memory_repo.get_all_core_memories(agent_id)
        }

        warnings = []
        for block_def in block_defs:
            memory = memories.get(block_def.block_name)
            if memory:
                percent = memory.get_capacity_percent(block_def.word_limit)
                if percent >= self.CAPACITY_WARNING_THRESHOLD * 100:
                    warnings.append({
                        "block_name": block_def.block_name,
                        "word_count": memory.word_count,
                        "word_limit": block_def.word_limit,
                        "percent": percent,
                    })
        return warnings

    def _build_warning_message(self, warnings: list[dict]) -> str:
        """Build system message for capacity warnings."""
        lines = [
            "<memory_warning>",
            "The following memory blocks are nearing capacity:",
        ]
        for w in warnings:
            lines.append(
                f"- [{w['block_name']}]: {w['word_count']}/{w['word_limit']} words "
                f"({w['percent']:.0f}%)"
            )

        lines.extend([
            "",
            "You should:",
            "1. Review and consolidate redundant information",
            "2. Move detailed information to archival memory",
            "3. Delete outdated entries",
            "",
            "If you don't take action, the system will auto-compact these blocks.",
            "</memory_warning>",
        ])
        return "\n".join(lines)
