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
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncIterator

from src.common import CAPACITY_WARNING_THRESHOLD
from src.agents.models import MemoryCapacityWarning
from src.connectors.mcp.service import MCPConnectorService
from src.agents.tool_audit import ToolCallStart, build_tool_call_audit_message
from src.agents.tool_execution import ToolExecutionRouter
from src.agents.tool_runtime import (
    ToolCommandCategory,
    ToolCommandRegistry,
    build_default_tool_command_registry,
)
from src.llm.conversation_strategy import FixedWindowStrategy
from src.llm.credentials import load_provider_credentials
from src.llm.events import SSEEvent, SSEEventType
from src.llm.providers import get_llm_provider
from src.memory import MemoryRepository
from src.messages.models import Message, Attachment
from src.messages.repositories import MessageRepository, get_message_repository
from src.memory.snapshot import CoreMemorySnapshot
from src.settings.repository import get_provider_settings_repository
from src.skills.models import AgentSkill
from src.skills.service import SkillRuntimeService
from src.tools.native import NativeToolHandler
from src.knowledge.repository import AgentKnowledgeBaseRepository

from .base import AgentArchitecture

if TYPE_CHECKING:
    from src.agents.runtime_state import AgentTurnState

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

    def __init__(
        self,
        max_context_words: int = 8000,
        *,
        message_repository: MessageRepository | None = None,
    ):
        """
        Initialize Krishna MemGPT architecture.

        Args:
            max_context_words: Maximum words to include in conversation context
        """
        self.max_context_words = max_context_words
        self.message_repo = message_repository or get_message_repository("dynamodb")
        self.memory_repo = MemoryRepository()
        self.provider_settings_repo = get_provider_settings_repository()
        self.agent_kb_repo = AgentKnowledgeBaseRepository()
        self.skill_runtime = SkillRuntimeService()
        self.mcp_connector_service = MCPConnectorService()
        self.tool_handler = NativeToolHandler(self.memory_repo, message_repo=self.message_repo)
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
                model_name=agent.agent_model or "",
                user_message=user_message,
                attachments=attachments or [],
            )

            state.linked_kb_ids = self._get_linked_kb_ids(agent.agent_id)
            self.tool_handler.set_knowledge_base_context(state.linked_kb_ids)

            state.enabled_skills = self.skill_runtime.list_enabled(agent.agent_id)
            try:
                state.enabled_mcp_connections = self.mcp_connector_service.list_agent_connections(
                    owner_email=owner_email,
                    agent_id=agent.agent_id,
                    enabled_only=True,
                    verify_agent=False,
                )
            except Exception as exc:
                log.warning("Failed to load enabled MCP connectors for agent %s: %s", agent.agent_id, exc)
                state.enabled_mcp_connections = []

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
            state.user_message_id = user_msg.message_id

            yield SSEEvent(
                event_type=SSEEventType.USER_MESSAGE_SAVED,
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

            state.credentials = await load_provider_credentials(
                provider_name=state.provider_name,
                provider_settings=provider_settings,
                provider_settings_repo=self.provider_settings_repo,
            )

            # 4. Load core memory and build system prompt
            yield SSEEvent(
                event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                content="Loading memory...",
            )

            kb_count = len(state.linked_kb_ids) if state.linked_kb_ids else None

            core_memory_snapshot = self._load_core_memory_snapshot(agent.agent_id, actor_id)
            capacity_warnings = self._check_capacity_warnings_from_snapshot(core_memory_snapshot)

            system_prompt = self._build_system_prompt(
                agent,
                actor_id,
                kb_count=kb_count,
                enabled_skills=state.enabled_skills or None,
                enabled_mcp_connections=state.enabled_mcp_connections or None,
                core_memory=core_memory_snapshot,
                capacity_warnings=capacity_warnings or None,
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

            from src.agents.agentic_loop import run_agentic_tool_loop

            tool_registry = self._build_tool_registry()
            state.tools = self._build_tool_definitions(state, tool_registry)
            tool_router = ToolExecutionRouter(
                skill_runtime=self.skill_runtime,
                mcp_runtime=self.mcp_connector_service,
                native_tools=self.tool_handler,
                registry=tool_registry,
            )

            full_response = ""
            tool_call_sequence = 0
            tool_call_starts: dict[str, ToolCallStart] = {}
            async for loop_event in run_agentic_tool_loop(
                provider=provider,
                context=context,
                credentials=state.credentials or {},
                tools=state.tools,
                model=state.model_name,
                tool_router=tool_router,
                state=state,
            ):
                if loop_event.kind == "text":
                    yield SSEEvent(
                        event_type=SSEEventType.AGENT_RESPONSE_TO_USER,
                        content=loop_event.payload["content"],
                    )

                elif loop_event.kind == "tool_call_start":
                    tool_call_sequence += 1
                    tool_call_id = loop_event.payload["tool_call_id"]
                    tool_call_starts[tool_call_id] = ToolCallStart(
                        sequence=tool_call_sequence,
                        tool_name=loop_event.payload["tool_name"],
                        tool_args=loop_event.payload["tool_args"],
                        started_at=datetime.now(timezone.utc),
                    )

                    yield SSEEvent(
                        event_type=SSEEventType.TOOL_CALL_START,
                        content=f"Calling {loop_event.payload['tool_name']}...",
                        tool_name=loop_event.payload["tool_name"],
                        tool_args=loop_event.payload["tool_args"],
                    )

                elif loop_event.kind == "tool_call_result":
                    tool_call_id = loop_event.payload["tool_call_id"]
                    result = loop_event.payload["result"]
                    start = tool_call_starts.get(tool_call_id)

                    if start:
                        audit = build_tool_call_audit_message(
                            tool_call_id=tool_call_id,
                            sequence=start.sequence,
                            tool_name=start.tool_name,
                            tool_args=start.tool_args,
                            result=result,
                            success=loop_event.payload["success"],
                            started_at=start.started_at,
                        )

                        self.message_repo.save(
                            Message(
                                conversation_id=conversation.conversation_id,
                                created_by=actor_email,
                                role="system",
                                content=audit.model_dump_json(),
                            )
                        )

                    # If a skill returns a UI payload, emit an explicit UI event.
                    # (The widget should render forms only when it receives UI_FORM_RENDER.)
                    try:
                        parsed = json.loads(result) if isinstance(result, str) else None
                    except Exception:
                        parsed = None

                    if isinstance(parsed, dict) and parsed.get("type") == "ui_form_render":
                        form = parsed.get("form") if isinstance(parsed.get("form"), dict) else None
                        submit_label = parsed.get("submit_label") if isinstance(parsed.get("submit_label"), str) else None

                        # Attempt to extract identifiers for analytics/readability.
                        form_label = None
                        form_id = None
                        if form:
                            form_label = form.get("form_name") if isinstance(form.get("form_name"), str) else None
                            form_id = form.get("form_id") if isinstance(form.get("form_id"), str) else None

                        yield SSEEvent(
                            event_type=SSEEventType.UI_FORM_RENDER,
                            content=form_label or "Form",
                            form=form,
                            submit_label=submit_label,
                            form_id=form_id,
                            form_label=form_label,
                        )

                    # Always emit a tool result for the timeline.
                    yield SSEEvent(
                        event_type=SSEEventType.TOOL_CALL_RESULT,
                        content=result,
                        tool_name=loop_event.payload["tool_name"],
                        success=loop_event.payload["success"],
                    )

                elif loop_event.kind == "prompt_refresh_needed":
                    # Core memory was mutated by tools; rebuild system prompt so the model
                    # sees the updated memory context on the next iteration.
                    refreshed_snapshot = self._load_core_memory_snapshot(agent.agent_id, actor_id)
                    refreshed_warnings = self._check_capacity_warnings_from_snapshot(refreshed_snapshot)

                    refreshed_prompt = self._build_system_prompt(
                        agent,
                        actor_id,
                        kb_count=kb_count,
                        enabled_skills=state.enabled_skills or None,
                        enabled_mcp_connections=state.enabled_mcp_connections or None,
                        core_memory=refreshed_snapshot,
                        capacity_warnings=refreshed_warnings or None,
                    )

                    # Replace the system prompt in-place.
                    if context and context[0].get("role") == "system":
                        context[0]["content"] = refreshed_prompt

                elif loop_event.kind == "runtime_event":
                    yield loop_event.payload["event"]

                elif loop_event.kind == "complete":
                    full_response = loop_event.payload["full_text"]

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
                    event_type=SSEEventType.ASSISTANT_MESSAGE_SAVED,
                    content="Assistant message saved",
                    message_id=assistant_msg.message_id,
                )

            yield SSEEvent(
                event_type=SSEEventType.STREAM_COMPLETE,
                content="Response complete",
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
        kb_count: int | None = None,
        enabled_skills: list[AgentSkill] | None = None,
        enabled_mcp_connections: list[Any] | None = None,
        core_memory: CoreMemorySnapshot | None = None,
        capacity_warnings: list[MemoryCapacityWarning] | None = None,
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
            kb_count=kb_count,
            enabled_skills=enabled_skills,
            enabled_mcp_connections=enabled_mcp_connections,
            core_memory=core_memory,
            capacity_warnings=capacity_warnings,
        )

    def _load_core_memory_snapshot(self, agent_id: str, user_id: str) -> CoreMemorySnapshot:
        """Load a consistent core-memory snapshot (single read) for this turn."""
        from src.memory.snapshot import (
            CoreMemoryBlockDefSnapshot,
            CoreMemoryBlockSnapshot,
            CoreMemorySnapshot,
        )

        block_defs = self.memory_repo.get_block_definitions(agent_id, user_id)
        memories = self.memory_repo.get_all_core_memories(agent_id, user_id)

        def_snaps = [
            CoreMemoryBlockDefSnapshot(
                block_name=d.block_name,
                description=d.description,
                word_limit=d.word_limit,
            )
            for d in block_defs
        ]

        block_snaps = {
            m.block_name: CoreMemoryBlockSnapshot(
                block_name=m.block_name,
                lines=list(m.lines or []),
                word_count=m.word_count,
            )
            for m in memories
        }

        return CoreMemorySnapshot(block_defs=def_snaps, blocks=block_snaps)

    def _check_capacity_warnings_from_snapshot(
        self,
        snapshot: CoreMemorySnapshot,
    ) -> list[MemoryCapacityWarning]:
        """Check capacity warnings from a snapshot (no DB reads)."""
        warnings: list[MemoryCapacityWarning] = []
        for d in snapshot.block_defs:
            b = snapshot.blocks.get(d.block_name)
            if not b:
                continue
            percent = (b.word_count / d.word_limit) * 100 if d.word_limit else 0
            if percent >= CAPACITY_WARNING_THRESHOLD * 100:
                warnings.append(
                    MemoryCapacityWarning(
                        block_name=d.block_name,
                        word_count=b.word_count,
                        word_limit=d.word_limit,
                        percent=percent,
                    )
                )
        return warnings

    # Capacity warning prompt rendering lives in CapacityWarningsLoader.

    def _build_tool_registry(self) -> ToolCommandRegistry:
        return build_default_tool_command_registry(
            skill_runtime=self.skill_runtime,
            native_tools=self.tool_handler,
            mcp_runtime=self.mcp_connector_service,
        )

    def _build_tool_definitions(
        self,
        state: "AgentTurnState",
        registry: ToolCommandRegistry,
    ) -> list[dict[str, Any]]:
        categories = {ToolCommandCategory.NATIVE}
        if state.linked_kb_ids:
            categories.add(ToolCommandCategory.KNOWLEDGE)
        if state.enabled_skills:
            categories.add(ToolCommandCategory.SKILL)
        if state.enabled_mcp_connections:
            categories.add(ToolCommandCategory.MCP)
        return registry.definitions_for_categories(categories)

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
