"""
Krishna MemGPT Agent Architecture.

An architecture with memory capabilities:
- Core memory (human/persona) loaded into context every turn
- Archival memory for long-term storage
- Native memory tools for read/write operations
- Agentic loop for tool execution
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncIterator, Iterator

from src.agents.agentic_loop import PromptRefreshNeeded, TurnComplete, run_agentic_tool_loop
from src.agents.models import MemoryCapacityWarning
from src.agents.provider_session import open_provider_session
from src.agents.runtime_state import AgentTurnState
from src.agents.tool_audit import ToolCallAuditLog
from src.agents.tool_execution import ToolExecutionRouter
from src.agents.tool_results import interpret_tool_result
from src.connectors.mcp.service import MCPConnectorService
from src.agents.tool_runtime import (
    ToolCategory,
    ToolRegistry,
    build_default_tool_registry,
)
from src.llm.conversation_strategy import FixedWindowStrategy
from src.llm.events import SSEEvent, SSEEventType
from src.memory import MemoryRepository
from src.messages.models import Message, MessageCanvasArtifact, Attachment
from src.messages.repositories import MessageRepository, get_message_repository
from src.memory.snapshot import (
    CoreMemoryBlockDefSnapshot,
    CoreMemoryBlockSnapshot,
    CoreMemorySnapshot,
)
from src.settings.repository import get_provider_settings_repository
from src.skills.models import AgentSkill
from src.skills.service import SkillRuntimeService
from src.tools.native import NativeToolHandler
from src.knowledge.repository import AgentKnowledgeBaseRepository

from .base import AgentArchitecture
from .krishna_memgpt_prompt import build_krishna_memgpt_system_prompt

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
        self.message_repo = message_repository or get_message_repository("dynamodb")
        self.memory_repo = MemoryRepository()
        self.provider_settings_repo = get_provider_settings_repository()
        self.agent_kb_repo = AgentKnowledgeBaseRepository()
        self.skill_runtime = SkillRuntimeService()
        self.mcp_connector_service = MCPConnectorService()
        self.tool_handler = NativeToolHandler(self.memory_repo, message_repo=self.message_repo)
        # The spec tables are module constants, so one registry serves every turn.
        self.tool_registry = build_default_tool_registry(
            skill_runtime=self.skill_runtime,
            native_tools=self.tool_handler,
            mcp_runtime=self.mcp_connector_service,
        )
        self.conversation_strategy = FixedWindowStrategy(max_words=max_context_words)

    @property
    def name(self) -> str:
        return "krishna-memgpt"

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

        session = await open_provider_session(
            agent,
            owner_email=state.owner_email,
            provider_settings_repo=self.provider_settings_repo,
        )
        state.credentials = session.credentials

        # 4. Load core memory and build system prompt
        yield SSEEvent(
            event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
            content="Loading memory...",
        )

        kb_count = len(state.linked_kb_ids) if state.linked_kb_ids else None
        system_prompt = self._build_memory_prompt(agent, actor_id, kb_count, state)

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

        tools = self.tool_registry.definitions_for_categories(_tool_categories_for(state))
        tool_router = ToolExecutionRouter(self.tool_registry)

        outputs = TurnOutputs()
        audit = ToolCallAuditLog(
            message_repo=self.message_repo,
            conversation_id=conversation.conversation_id,
            actor_email=actor_email,
        )

        async for item in run_agentic_tool_loop(
            provider=session.provider,
            context=context,
            credentials=state.credentials or {},
            tools=tools,
            model=state.model_name,
            tool_router=tool_router,
            state=state,
        ):
            if isinstance(item, TurnComplete):
                outputs.full_text = item.full_text
                continue

            if isinstance(item, PromptRefreshNeeded):
                # Tools changed core memory, so the next call must not see the
                # snapshot rendered from before they ran.
                context[0]["content"] = self._build_memory_prompt(agent, actor_id, kb_count, state)
                continue

            yield item
            for event in outputs.absorb(item):
                yield event

            audit.observe(item)
            if item.event_type == SSEEventType.ERROR:
                return

        assistant_text = outputs.assistant_text
        if not assistant_text.strip():
            return

        # Substituted text has not been streamed yet; the model's own has.
        if not outputs.full_text.strip():
            yield SSEEvent(
                event_type=SSEEventType.AGENT_RESPONSE_TO_USER,
                content=assistant_text,
            )

        assistant_msg = Message(
            conversation_id=conversation.conversation_id,
            created_by=actor_email,
            role="assistant",
            content=assistant_text,
            canvases=outputs.canvases,
        )
        self.message_repo.save(assistant_msg)
        yield SSEEvent(
            event_type=SSEEventType.ASSISTANT_MESSAGE_SAVED,
            content="Assistant message saved",
            message_id=assistant_msg.message_id,
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
        *,
        kb_count: int | None = None,
        enabled_skills: list[AgentSkill] | None = None,
        enabled_mcp_connections: list[Any] | None = None,
        core_memory: CoreMemorySnapshot | None = None,
        capacity_warnings: list[MemoryCapacityWarning] | None = None,
    ) -> str:
        """Build the system prompt, rendered from data already loaded this turn."""
        return build_krishna_memgpt_system_prompt(
            agent_persona=agent.agent_persona,
            kb_count=kb_count,
            enabled_skills=enabled_skills,
            enabled_mcp_connections=enabled_mcp_connections,
            core_memory=core_memory,
            capacity_warnings=capacity_warnings,
        )

    def _build_memory_prompt(
        self,
        agent: "Agent",
        actor_id: str,
        kb_count: int | None,
        state: AgentTurnState,
    ) -> str:
        """Render the system prompt from a fresh core-memory snapshot.

        Used for the first render and for every refresh after a memory write,
        so the two can never drift apart.
        """
        snapshot = self._load_core_memory_snapshot(agent.agent_id, actor_id)
        return self._build_system_prompt(
            agent,
            kb_count=kb_count,
            enabled_skills=state.enabled_skills or None,
            enabled_mcp_connections=state.enabled_mcp_connections or None,
            core_memory=snapshot,
            capacity_warnings=self._check_capacity_warnings_from_snapshot(snapshot) or None,
        )

    def _load_core_memory_snapshot(self, agent_id: str, user_id: str) -> CoreMemorySnapshot:
        """Load a consistent core-memory snapshot (single read) for this turn."""
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
        word_limits = {d.block_name: d.word_limit for d in block_defs}

        block_snaps = {
            m.block_name: CoreMemoryBlockSnapshot(
                block_name=m.block_name,
                lines=list(m.lines or []),
                word_count=m.word_count,
                word_limit=word_limits.get(m.block_name, 0),
            )
            for m in memories
        }

        return CoreMemorySnapshot(block_defs=def_snaps, blocks=block_snaps)

    def _check_capacity_warnings_from_snapshot(
        self,
        snapshot: CoreMemorySnapshot,
    ) -> list[MemoryCapacityWarning]:
        """Blocks the snapshot reports as nearing capacity (no DB reads)."""
        blocks = (snapshot.blocks.get(d.block_name) for d in snapshot.block_defs)
        return [
            MemoryCapacityWarning(
                block_name=block.block_name,
                word_count=block.word_count,
                word_limit=block.word_limit,
                percent=block.fill_percent,
            )
            for block in blocks
            if block and block.nearing_capacity
        ]

    def _get_linked_kb_ids(self, agent_id: str) -> list[str]:
        """Get list of knowledge base IDs linked to this agent."""
        try:
            links = self.agent_kb_repo.find_kbs_for_agent(agent_id)
            return [link.kb_id for link in links]
        except Exception as e:
            log.warning(f"Failed to load linked KBs for agent {agent_id}: {e}")
            return []


def _tool_categories_for(state: AgentTurnState) -> set[ToolCategory]:
    """Only tell the model about the tool families this agent can actually use."""
    return {
        ToolCategory.NATIVE,
        *([ToolCategory.KNOWLEDGE] if state.linked_kb_ids else []),
        *([ToolCategory.SKILL] if state.enabled_skills else []),
        *([ToolCategory.MCP] if state.enabled_mcp_connections else []),
    }


TOOL_TURN_FALLBACK_MESSAGE = (
    "The tools finished running, but I could not produce a final response from their results. "
    "Please ask me to continue or retry the request."
)


@dataclass
class TurnOutputs:
    """What the architecture accumulates while the loop streams."""

    full_text: str = ""
    canvases: list[MessageCanvasArtifact] = field(default_factory=list)
    #: Wording to use when the model itself produced no text.
    fallback_text: str | None = None
    had_tool_call: bool = False
    #: A tool already answered the user on its own -- a generated image, say --
    #: so silence from the model is not a failure.
    answered_without_text: bool = False

    def absorb(self, event: SSEEvent) -> Iterator[SSEEvent]:
        """Take what this event contributes, yielding any events it implies."""
        if event.event_type == SSEEventType.TOOL_CALL_START:
            self.had_tool_call = True
        elif event.event_type == SSEEventType.IMAGE_GENERATION_COMPLETE:
            self.answered_without_text = True
        elif event.event_type == SSEEventType.TOOL_CALL_RESULT:
            for interpreted in interpret_tool_result(event.content):
                if interpreted.canvas:
                    self.canvases.append(interpreted.canvas)
                self.fallback_text = self.fallback_text or interpreted.fallback_text
                if interpreted.event:
                    yield interpreted.event

    @property
    def assistant_text(self) -> str:
        """What to persist as the assistant's reply, substituting if it said nothing."""
        if self.full_text.strip():
            return self.full_text
        if self.fallback_text:
            return self.fallback_text
        if self.had_tool_call and not self.answered_without_text:
            return TOOL_TURN_FALLBACK_MESSAGE
        return ""
