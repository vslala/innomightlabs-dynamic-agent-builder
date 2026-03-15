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
from typing import TYPE_CHECKING, Any, AsyncIterator

from src.common import CAPACITY_WARNING_THRESHOLD, MAX_TOOL_ITERATIONS
from src.crypto import decrypt
from src.auth.openai_oauth import ensure_valid_openai_credentials
from src.llm.conversation_strategy import FixedWindowStrategy
from src.llm.events import SSEEvent, SSEEventType
from src.llm.providers import get_llm_provider
from src.memory import MemoryRepository, CoreMemory
from src.messages.models import Message, Attachment
from src.messages.repository import MessageRepository
from src.settings.repository import get_provider_settings_repository
from src.skills.service import SkillRuntimeService
from src.tools.native import NATIVE_TOOLS, KNOWLEDGE_TOOLS, NativeToolHandler
from src.knowledge.repository import AgentKnowledgeBaseRepository

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

    def __init__(self, max_context_words: int = 8000):
        """
        Initialize Krishna MemGPT architecture.

        Args:
            max_context_words: Maximum words to include in conversation context
        """
        self.max_context_words = max_context_words
        self.message_repo = MessageRepository()
        self.memory_repo = MemoryRepository()
        self.provider_settings_repo = get_provider_settings_repository()
        self.agent_kb_repo = AgentKnowledgeBaseRepository()
        self.skill_runtime = SkillRuntimeService()
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
        owner_email: str,
        actor_email: str,
        actor_id: str,
        attachments: list[Attachment] | None = None,
    ) -> AsyncIterator[SSEEvent]:
        """
        Handle a user message with memory-augmented conversation.

        Args:
            agent: The agent handling this conversation
            conversation: The conversation context
            user_message: The user's message content
            owner_email: The agent owner's email (used for provider settings lookup)
            actor_email: The end-user's email (who is speaking)
            actor_id: The end-user's ID (for memory scoping)
            attachments: Optional list of file attachments

        Yields:
            SSEEvent objects for streaming to the client
        """
        try:
            from src.agents.runtime_state import AgentTurnState

            self.tool_handler.set_conversation_context(conversation.conversation_id)
            self.tool_handler.set_user_context(actor_id)

            state = AgentTurnState(
                owner_email=owner_email,
                actor_email=actor_email,
                actor_id=actor_id,
                conversation_id=conversation.conversation_id,
                agent_id=agent.agent_id,
                provider_name=agent.agent_provider,
                model_name=agent.agent_model,
                user_message=user_message,
                attachments=attachments or [],
            )

            state.linked_kb_ids = self._get_linked_kb_ids(agent.agent_id)
            self.tool_handler.set_knowledge_base_context(state.linked_kb_ids)

            state.enabled_skills = self.skill_runtime.list_enabled(agent.agent_id)

            self._ensure_memory_initialized(agent.agent_id, actor_id)

            # 2. Save user message (with attachments if any)
            user_msg = Message(
                conversation_id=state.conversation_id,
                created_by=state.actor_email,
                role="user",
                content=state.user_message,
                attachments=state.attachments,
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
                state.owner_email, state.provider_name
            )
            if not provider_settings:
                yield SSEEvent(
                    event_type=SSEEventType.ERROR,
                    content=f"Provider '{state.provider_name}' is not configured. "
                            "Please configure it in Settings > Provider Configuration.",
                )
                return

            if state.provider_name == "OpenAI":
                openai_credentials = await ensure_valid_openai_credentials(
                    provider_settings,
                    self.provider_settings_repo,
                )
                state.credentials = openai_credentials.model_dump(mode="json")
            else:
                state.credentials = json.loads(decrypt(provider_settings.encrypted_credentials))

            # 4. Load core memory and build system prompt
            yield SSEEvent(
                event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                content="Loading memory...",
            )

            kb_instructions = (
                self._build_kb_instructions(len(state.linked_kb_ids))
                if state.linked_kb_ids
                else None
            )
            skills_addendum = (
                self.skill_runtime.build_system_prompt_addendum(state.enabled_skills)
                if state.enabled_skills
                else None
            )

            system_prompt = self._build_system_prompt(
                agent,
                actor_id,
                kb_instructions=kb_instructions,
                skills_addendum=skills_addendum,
            )

            # 5. Build conversation context
            yield SSEEvent(
                event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                content="Building conversation context...",
            )

            all_messages = self.message_repo.find_by_conversation(
                conversation.conversation_id
            )
            context: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
            # Pass session_timeout_minutes to filter messages by time gap
            context.extend(
                self.conversation_strategy.build_context(
                    all_messages,
                    session_timeout_minutes=agent.session_timeout_minutes,
                )
            )

            yield SSEEvent(
                event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                content="Connecting to AI model...",
            )

            provider = get_llm_provider(state.provider_name)

            state.tools = NATIVE_TOOLS.copy()
            if state.linked_kb_ids:
                state.tools.extend(KNOWLEDGE_TOOLS)
            if state.enabled_skills:
                state.tools.extend(self.skill_runtime.build_skill_tools())

            from src.agents.tool_execution import ToolExecutionRouter

            tool_router = ToolExecutionRouter(
                skill_runtime=self.skill_runtime,
                native_tools=self.tool_handler,
            )

            full_response = ""
            for iteration in range(MAX_TOOL_ITERATIONS):
                has_tool_calls = False
                pending_tool_calls = []
                iteration_text = ""

                async for event in provider.stream_response(
                    context,
                    state.credentials or {},
                    state.tools,
                    state.model_name,
                ): # pyright: ignore[reportGeneralTypeIssues]
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
                        outcome = await tool_router.execute(
                            tool_name=tool_event.tool_name,
                            tool_input=tool_event.tool_input,
                            tool_use_id=tool_event.tool_use_id,
                            state=state,
                        )

                        # Emit tool result event for UI timeline
                        yield SSEEvent(
                            event_type=SSEEventType.TOOL_CALL_RESULT,
                            content=outcome.result[:200] + "..." if len(outcome.result) > 200 else outcome.result,
                            tool_name=tool_event.tool_name,
                            success=outcome.success,
                        )

                        tool_results.append({
                            "toolResult": {
                                "toolUseId": tool_event.tool_use_id,
                                "content": [{"text": outcome.result}],
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
                    created_by=actor_email,
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

    def _ensure_memory_initialized(self, agent_id: str, user_id: str) -> None:
        """Ensure default memory blocks exist for this agent."""
        block_defs = self.memory_repo.get_block_definitions(agent_id, user_id)
        if not block_defs:
            self.memory_repo.initialize_default_blocks(agent_id, user_id)
            log.info(f"Initialized default memory blocks for agent {agent_id}")

    def _build_system_prompt(
        self,
        agent: "Agent",
        user_id: str,
        *,
        kb_instructions: str | None = None,
        skills_addendum: str | None = None,
    ) -> str:
        """Build the system prompt.

        This wrapper keeps the architecture readable by delegating prompt
        construction to a dedicated module.
        """
        from .krishna_memgpt_prompt import build_krishna_memgpt_system_prompt

        return build_krishna_memgpt_system_prompt(
            agent_persona=agent.agent_persona,
            memory_repo=self.memory_repo,
            agent_id=agent.agent_id,
            user_id=user_id,
            kb_instructions=kb_instructions,
            skills_addendum=skills_addendum,
        )

    def _check_capacity_warnings(self, agent_id: str, user_id: str) -> list[dict]:
        """Check for memory blocks at or above warning threshold."""
        block_defs = self.memory_repo.get_block_definitions(agent_id, user_id)
        memories = {
            m.block_name: m
            for m in self.memory_repo.get_all_core_memories(agent_id, user_id)
        }

        warnings = []
        for block_def in block_defs:
            memory = memories.get(block_def.block_name)
            if memory:
                percent = memory.get_capacity_percent(block_def.word_limit)
                if percent >= CAPACITY_WARNING_THRESHOLD * 100:
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

    def _format_content_with_attachments(
        self, content: str, attachments: list[Attachment]
    ) -> str:
        """
        Format message content with attachments for LLM context.

        Args:
            content: The message text content
            attachments: List of file attachments

        Returns:
            Formatted content with attachments prepended
        """
        if not attachments:
            return content

        attachment_sections = []
        for att in attachments:
            attachment_sections.append(
                f'<attached_file name="{att.filename}">\n{att.content}\n</attached_file>'
            )

        attachments_text = "\n\n".join(attachment_sections)
        return f"{attachments_text}\n\n{content}"

    def _get_linked_kb_ids(self, agent_id: str) -> list[str]:
        """Get list of knowledge base IDs linked to this agent."""
        try:
            links = self.agent_kb_repo.find_kbs_for_agent(agent_id)
            return [link.kb_id for link in links]
        except Exception as e:
            log.warning(f"Failed to load linked KBs for agent {agent_id}: {e}")
            return []

    def _build_kb_instructions(self, kb_count: int) -> str:
        """Build instructions for knowledge base search tool."""
        return f"""<knowledge_base>
You have access to {kb_count} knowledge base(s) containing documentation, FAQs, and other content.

Use the knowledge_base_search tool when:
- The user asks about products, features, or services
- The user needs information that might be in documentation
- The user asks "how do I..." or "what is..." questions about topics covered in the knowledge base
- You're unsure about factual information that the knowledge base might contain

The tool will return relevant text chunks with source URLs. Use these to provide accurate, sourced answers.
</knowledge_base>"""
