"""
Krishna MemGPT Agent Architecture.

An architecture with memory capabilities:
- Core memory (human/persona) loaded into context every turn
- Archival memory for long-term storage
- Native memory tools for read/write operations
- Agentic loop for tool execution
"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncIterator, Iterator

from src.agents.agentic_loop import PromptRefreshNeeded, TurnComplete, run_agentic_tool_loop
from src.agents.instructions import MacroContext, expand_instructions
from src.agents.models import MemoryCapacityWarning
from src.agents.provider_session import open_provider_session
from src.agents.runtime_state import AgentTurnState
from src.agents.tool_audit import ToolCallAuditLog
from src.agents.tool_execution import ToolExecutionRouter
from src.agents.tool_results import interpret_tool_result
from src.agents.tool_runtime import build_default_tool_registry
from src.agents.tool_runtime.families import ToolFamily, active_families, prompt_sections
from src.connectors.mcp.service import MCPConnectorService
from src.knowledge.access import readable_by_agent
from src.knowledge.repository import AgentKnowledgeBaseRepository, KnowledgeBaseRepository
from src.llm.conversation_strategy import FixedWindowStrategy
from src.llm.events import SSEEvent, SSEEventType
from src.memory import MemoryRepository
from src.memory.snapshot import CoreMemorySnapshot
from src.messages.models import Attachment, ImageAttachment, Message, MessageCanvasArtifact, MessageReference
from src.messages.references import reference_tags, references_by_kind
from src.messages.repositories import MessageRepository, get_message_repository
from src.settings.repository import get_provider_settings_repository
from src.skills.models import ActorKind, LoadedSkillRuntimeResponse
from src.skills.service import SkillRuntimeService
from src.tools.native import NativeToolHandler
from src.vision.context import index_images
from src.vision.policy import image_input_availability

from .base import AgentArchitecture
from .krishna_memgpt_families import TOOL_FAMILIES
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
        self.kb_repo = KnowledgeBaseRepository()
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
        actor_kind: ActorKind,
        attachments: list[Attachment] | None = None,
        images: list[ImageAttachment] | None = None,
        references: list[MessageReference] | None = None,
        api_key_id: str | None = None,
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
            actor_kind: Who the end-user is to the agent; decides which skills and MCP tools they get
            attachments: Optional list of file attachments
            images: Images the user sent with the message, already uploaded (read through `read_image`)
            references: What the message points at (documents), already attached by their kinds
            api_key_id: The public API secret key the turn runs under, if any

        Yields:
            SSEEvent objects for streaming to the client
        """
        state = AgentTurnState(
            owner_email=owner_email,
            actor_email=actor_email,
            actor_id=actor_id,
            actor_kind=actor_kind,
            conversation_id=conversation.conversation_id,
            agent_id=agent.agent_id,
            model_name=agent.agent_model or "",
            user_message=user_message,
            attachments=attachments or [],
            api_key_id=api_key_id,
            conversation_context=conversation.context,
            account_id=agent.account_id,
            owner_id=agent.owner_id,
        )

        state.linked_kb_ids = self._get_linked_kb_ids(agent)

        state.enabled_skills = self.skill_runtime.list_usable(agent.agent_id, actor_kind)
        state.instructions = expand_instructions(
            agent.agent_persona,
            MacroContext(agent.account_id, frozenset(skill.skill_id for skill in state.enabled_skills)),
        )
        state.enabled_mcp_connections = self._mcp_connections_for(state)

        # Save the user message (with attachments if any)
        user_msg = Message(
            conversation_id=state.conversation_id,
            created_by=state.actor_email,
            role="user",
            content=state.user_message,
            attachments=state.attachments,
            image_attachments=images or [],
            references=references or [],
        )
        self.message_repo.save(user_msg)
        state.user_message_id = user_msg.message_id

        yield SSEEvent(
            event_type=SSEEventType.USER_MESSAGE_SAVED,
            content="User message saved",
            message_id=user_msg.message_id,
        )

        # Provider settings
        yield SSEEvent(
            event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
            content="Loading provider configuration...",
        )

        session = await open_provider_session(
            agent,
            provider_settings_repo=self.provider_settings_repo,
        )

        # Conversation context (first: the system prompt depends on it)
        yield SSEEvent(
            event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
            content="Building conversation context...",
        )

        all_messages = self.message_repo.find_by_conversation(
            conversation.conversation_id
        )
        # Every image and reference in the conversation, not just the context window's: their tools can open any
        state.images = index_images(all_messages)
        state.image_input_available = bool(state.images) and image_input_availability(agent).available
        state.references = references_by_kind(all_messages)
        history = self.conversation_strategy.build_context(
            all_messages,
            session_timeout_minutes=agent.session_timeout_minutes,
            reference_tags=reference_tags(conversation, state.references),
        )
        state.recent_skill_actions = self._recent_skill_actions(state, history)

        # The tool families this turn offers decide its tools, what may run, and their prompt sections
        families = active_families(TOOL_FAMILIES, state)
        offered = {family.category for family in families}

        # Core memory, then the system prompt
        yield SSEEvent(
            event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
            content="Loading memory...",
        )
        system_prompt = self._build_memory_prompt(agent, actor_id, state, families)
        context: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}, *history]

        yield SSEEvent(
            event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
            content="Connecting to AI model...",
        )

        tools = self.tool_registry.definitions_for_categories(offered)
        tool_router = ToolExecutionRouter(self.tool_registry, offered=offered)

        outputs = TurnOutputs()
        audit = ToolCallAuditLog(
            message_repo=self.message_repo,
            conversation_id=conversation.conversation_id,
            actor_email=actor_email,
        )

        async for item in run_agentic_tool_loop(
            provider=session.provider,
            context=context,
            credentials=session.credentials,
            tools=tools,
            model=state.model_name,
            tool_router=tool_router,
            state=state,
        ):
            if isinstance(item, TurnComplete):
                outputs.full_text = item.full_text
                outputs.stop_reason = item.stop_reason
                continue

            if isinstance(item, PromptRefreshNeeded):
                # Tools changed core memory, so the next call must not see the
                # snapshot rendered from before they ran.
                context[0]["content"] = self._build_memory_prompt(agent, actor_id, state, families)
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


    def _build_memory_prompt(
        self,
        agent: "Agent",
        actor_id: str,
        state: AgentTurnState,
        families: list[ToolFamily],
    ) -> str:
        """Render the system prompt from a fresh core-memory snapshot.

        Used for the first render and for every refresh after a memory write,
        so the two can never drift apart.
        """
        snapshot = self._load_core_memory_snapshot(agent.agent_id, actor_id)
        return build_krishna_memgpt_system_prompt(
            agent_persona=state.instructions,
            conversation_context=state.conversation_context,
            core_memory=snapshot,
            capacity_warnings=_capacity_warnings(snapshot) or None,
            tool_sections=prompt_sections(families, state),
        )

    def _recent_skill_actions(
        self,
        state: AgentTurnState,
        history: list[dict[str, Any]],
    ) -> list[LoadedSkillRuntimeResponse]:
        """Schemas of recently used skill actions, so the agent need not reload them.

        A history holding only this turn's message is a fresh session (new, or reset by
        the session timeout), which starts without them.
        """
        if not state.enabled_skills or len(history) <= 1:
            return []
        audit, _, _ = self.message_repo.find_audit_by_conversation(
            state.conversation_id,
            limit=self.skill_runtime.RECENT_AUDIT_WINDOW,
        )
        return self.skill_runtime.recent_actions(audit, state.enabled_skills)

    def _load_core_memory_snapshot(self, agent_id: str, user_id: str) -> CoreMemorySnapshot:
        """One consistent read of core memory, initialising the blocks if absent."""
        block_defs = self.memory_repo.get_block_definitions(agent_id, user_id)
        if not block_defs:
            self.memory_repo.initialize_default_blocks(agent_id, user_id)
            log.info("Initialized default memory blocks for agent %s", agent_id)
            block_defs = self.memory_repo.get_block_definitions(agent_id, user_id)

        return CoreMemorySnapshot.of(
            block_defs, self.memory_repo.get_all_core_memories(agent_id, user_id)
        )

    def _mcp_connections_for(self, state: AgentTurnState) -> list[Any]:
        """The owner gets every enabled connector; anyone else only what the owner shared with them."""
        try:
            return self.mcp_connector_service.list_agent_connections(
                account_id=state.account_id,
                agent_id=state.agent_id,
                actor_kind=state.actor_kind,
                enabled_only=True,
                verify_agent=False,
            )
        except Exception as exc:
            log.warning("Failed to load enabled MCP connectors for agent %s: %s", state.agent_id, exc)
            return []

    def _get_linked_kb_ids(self, agent: "Agent") -> list[str]:
        """The linked knowledge bases the agent's owner can read, in its account. Nothing else is searched."""
        try:
            links = self.agent_kb_repo.find_kbs_for_agent(agent.agent_id)
            return [kb.kb_id for kb in readable_by_agent(agent, [link.kb_id for link in links], self.kb_repo)]
        except Exception as e:
            log.warning(f"Failed to load linked KBs for agent {agent.agent_id}: {e}")
            return []


def _capacity_warnings(snapshot: CoreMemorySnapshot) -> list[MemoryCapacityWarning]:
    """The prompt-facing shape of the snapshot's own capacity verdict."""
    return [
        MemoryCapacityWarning(
            block_name=block.block_name,
            word_count=block.word_count,
            word_limit=block.word_limit,
            percent=block.fill_percent,
        )
        for block in snapshot.nearing_capacity
    ]


#: Why the model gave no summary, in words the user (and the next turn) can act on.
WHY_NO_SUMMARY = {
    "max_tokens": "the model reached its output limit before it could write a summary",
    "content_filter": "the provider's content filter blocked the summary",
}


@dataclass
class TurnOutputs:
    """What the architecture accumulates while the loop streams."""

    full_text: str = ""
    stop_reason: str = "end_turn"
    canvases: list[MessageCanvasArtifact] = field(default_factory=list)
    #: Wording to use when the model itself produced no text.
    fallback_text: str | None = None
    #: How often each tool ran this turn, by the name the user sees.
    tool_runs: Counter[str] = field(default_factory=Counter)
    failed_tool_runs: int = 0
    #: A tool already answered the user on its own -- a generated image, say --
    #: so silence from the model is not a failure.
    answered_without_text: bool = False

    def absorb(self, event: SSEEvent) -> Iterator[SSEEvent]:
        """Take what this event contributes, yielding any events it implies."""
        if event.event_type == SSEEventType.IMAGE_GENERATION_COMPLETE:
            self.answered_without_text = True
        elif event.event_type == SSEEventType.TOOL_CALL_RESULT:
            self.tool_runs[event.display_tool_name or event.tool_name or "tool"] += 1
            if event.success is False:
                self.failed_tool_runs += 1
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
        if self.tool_runs and not self.answered_without_text:
            return self.record_of_tool_runs()
        return ""

    def record_of_tool_runs(self) -> str:
        """Saved when the model could not answer, so the next turn still knows what already ran."""
        count = sum(self.tool_runs.values())
        calls = "1 tool call" if count == 1 else f"{count} tool calls"
        runs = ", ".join(name if times == 1 else f"{name} ×{times}" for name, times in self.tool_runs.most_common())
        failed = f"; {self.failed_tool_runs} failed" if self.failed_tool_runs else ""
        why = WHY_NO_SUMMARY.get(self.stop_reason, "I couldn't write a summary of them")
        return (
            f"I ran {calls} ({runs}{failed}), but {why}. "
            "Ask me to summarise what was done; I won't run them again unless you ask."
        )
