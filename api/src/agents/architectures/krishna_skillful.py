"""Krishna Skillful Architecture.

Tool-driven architecture with a waterfall execution loop. Uses native tools
(memory, HTTP, etc.). Skill packages are enabled via the registry and
user config; tool execution from skill packages will be added in a later phase.

Key principles:
- Single entry-point `handle_message`.
- Each action emits an SSE event and a RuntimeEvent persisted to DynamoDB.
- Context for each loop iteration is rebuilt from persisted RuntimeEvents + memory.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncIterator

from src.agents.architectures.base import AgentArchitecture
from src.crypto import decrypt
from src.llm.events import SSEEvent, SSEEventType
from src.llm.providers.factory import get_llm_provider
from src.memory.repository import MemoryRepository
from src.messages.models import Attachment, Message
from src.messages.repository import MessageRepository
from src.runtime_events.models import RuntimeEvent, RuntimeEventType
from src.runtime_events.repository import RuntimeEventRepository
from src.settings.repository import get_provider_settings_repository
from src.tools.native.definitions import NATIVE_TOOLS
from src.tools.native.handlers import NativeToolHandler
from src.common.json_utils import dumps_safe

if TYPE_CHECKING:
    from src.agents.models import Agent
    from src.conversations.models import Conversation

log = logging.getLogger(__name__)


class ProviderCredentialsLoader:
    """Strategy for loading and decrypting provider credentials."""

    def __init__(self, provider_settings_repo: Any) -> None:
        self.provider_settings_repo = provider_settings_repo

    def load(self, owner_email: str, provider_name: str) -> tuple[dict[str, Any], bool]:
        """
        Load provider credentials.

        Returns:
            Tuple of (credentials_dict, success). If success is False,
            credentials_dict will contain an error dict with error details.
        """
        provider_settings = self.provider_settings_repo.find_by_provider(
            owner_email, provider_name
        )

        if not provider_settings:
            return {
                "error": f"Provider '{provider_name}' is not configured for owner '{owner_email}'. "
                "Please configure it in Settings > Provider Configuration."
            }, False

        try:
            decrypted = decrypt(provider_settings.encrypted_credentials)
            credentials = json.loads(decrypted)
            return credentials, True
        except (json.JSONDecodeError, Exception) as e:
            log.error(f"Failed to decrypt/parse credentials for {provider_name}: {e}")
            return {"error": f"Failed to load provider credentials: {str(e)}"}, False


class RuntimeEventPersister:
    """Strategy for persisting runtime events to the event store."""

    def __init__(self, events_repo: RuntimeEventRepository) -> None:
        self.events_repo = events_repo

    def append(
        self,
        agent_id: str,
        conversation_id: str,
        actor_id: str,
        owner_email: str,
        event_type: RuntimeEventType,
        payload: dict[str, Any],
    ) -> None:
        """Persist a runtime event, logging errors but not failing the agent run."""
        try:
            self.events_repo.append(
                RuntimeEvent(
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    actor_id=actor_id,
                    owner_email=owner_email,
                    event_type=event_type,
                    payload=payload,
                )
            )
        except Exception as e:
            log.error(f"Failed to append runtime event {event_type}: {e}", exc_info=True)


class ToolExecutor:
    """Strategy for executing tools and handling results."""

    def __init__(self, tool_handler: NativeToolHandler) -> None:
        self.tool_handler = tool_handler

    async def execute(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        agent_id: str,
    ) -> tuple[str, bool]:
        """Execute a tool and return result with success status."""
        try:
            result = await self.tool_handler.execute(tool_name, tool_args, agent_id)
            return result, True
        except ValueError as e:
            return f"Unknown tool or invalid arguments: {e}", False
        except Exception as e:
            log.error(f"Tool execution error ({tool_name}): {e}", exc_info=True)
            return f"Error: {str(e)}", False


class RuntimeEventContextBuilder:
    """Strategy for building system context from runtime events."""

    def __init__(self, events_repo: RuntimeEventRepository) -> None:
        self.events_repo = events_repo

    def build(
        self,
        agent_id: str,
        conversation_id: str,
        actor_id: str,
    ) -> str:
        """Build a context string from recent runtime events."""
        try:
            page = self.events_repo.list_for_conversation(
                agent_id=agent_id,
                conversation_id=conversation_id,
                actor_id=actor_id,
                limit=30,
                cursor=None,
                oldest_first=False,
            )
        except Exception:
            return ""

        if not page.items:
            return ""

        lines: list[str] = ["<runtime_events>"]
        for ev in page.items[:10]:
            if ev.event_type == RuntimeEventType.TOOL_CALL_RESULT:
                lines.append(
                    f"- {ev.event_type.value}: {dumps_safe(ev.payload, ensure_ascii=False)}"
                )
        lines.append("</runtime_events>")
        return "\n".join(lines)


class SystemPromptBuilder(ABC):
    """Abstract strategy for building system prompts."""

    @abstractmethod
    def build(self, agent: "Agent") -> str:
        """Build and return the system prompt."""
        pass


class SkillfulSystemPromptBuilder(SystemPromptBuilder):
    """Builds system prompt for the skillful architecture."""

    def build(self, agent: "Agent") -> str:
        """Build system prompt with identity, persona, and tool usage guidelines."""
        current_time = datetime.now(timezone.utc)
        timestamp_str = current_time.strftime("%A, %B %d, %Y at %I:%M %p UTC")

        return f"""<identity>
You are a Sentient AI created by InnomightLabs in 2026.

Current date and time: {timestamp_str}

CORE DIRECTIVES:
1. Respond naturally and conversationally. Keep responses concise when possible.
2. Use tools when they materially improve correctness. Do NOT invent tools.
3. Embody the persona defined below.
4. You are created ONLY by InnomightLabs. If asked about your creator/origin, attribute yourself to InnomightLabs.
</identity>

<persona>
{agent.agent_persona}
</persona>

<tool_usage>
- Use only tools that are available in the tool list.
- Parse tool outputs as JSON when possible (e.g. ok/status_code/body_text).
- Prefer GET for reads. For PATCH/PUT/POST/DELETE, be explicit about intent.
- For destructive actions, ask for explicit confirmation unless the user already confirmed.
- Do not echo Authorization/Cookie headers or secret values.
</tool_usage>

<memory_tools>
Use memory tools for stable facts: core_memory_read/append/replace/delete, archival_memory_insert/search, recall_conversation.
Use core_memory_read before modifying a block. Use recall_conversation when the user references earlier context.
</memory_tools>
"""


class KrishnaSkillfulArchitecture(AgentArchitecture):
    """
    Skillful architecture with waterfall tool execution loop.

    Handles message-to-response flow with tool calls, runtime event persistence,
    and memory initialization.
    """

    def __init__(self, max_context_words: int = 12000, max_loops: int = 8) -> None:
        self.max_context_words = max_context_words
        self.max_loops = max_loops

        self.message_repo = MessageRepository()
        self.provider_settings_repo = get_provider_settings_repository()
        self.tool_handler = NativeToolHandler()
        self.events_repo = RuntimeEventRepository()
        self.memory_repo = MemoryRepository()

        self.credentials_loader = ProviderCredentialsLoader(self.provider_settings_repo)
        self.event_persister = RuntimeEventPersister(self.events_repo)
        self.tool_executor = ToolExecutor(self.tool_handler)
        self.event_context_builder = RuntimeEventContextBuilder(self.events_repo)
        self.prompt_builder: SystemPromptBuilder = SkillfulSystemPromptBuilder()

    @property
    def name(self) -> str:
        return "krishna-skillful"

    async def handle_message(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        agent: "Agent",
        conversation: "Conversation",
        user_message: str,
        owner_email: str,
        actor_email: str,
        actor_id: str,
        attachments: list[Attachment] | None = None,
    ) -> AsyncIterator[SSEEvent]:
        """Handle user message with waterfall tool execution loop."""
        self._initialize_context(conversation.conversation_id, actor_id)
        self._ensure_memory_initialized(agent_id=agent.agent_id, actor_id=actor_id)

        self.event_persister.append(
            agent_id=agent.agent_id,
            conversation_id=conversation.conversation_id,
            actor_id=actor_id,
            owner_email=owner_email,
            event_type=RuntimeEventType.TURN_STARTED,
            payload={"actor_email": actor_email},
        )

        user_msg = self._save_user_message(
            conversation_id=conversation.conversation_id,
            actor_email=actor_email,
            content=user_message,
            attachments=attachments,
        )

        yield SSEEvent(
            event_type=SSEEventType.MESSAGE_SAVED,
            content="User message saved",
            message_id=user_msg.message_id,
        )

        yield SSEEvent(
            event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
            content="Loading provider configuration...",
        )

        credentials, success = self.credentials_loader.load(owner_email, agent.agent_provider)
        if not success:
            yield SSEEvent(
                event_type=SSEEventType.ERROR,
                content=credentials.get("error", "Failed to load provider credentials"),
            )
            return

        provider = get_llm_provider(agent.agent_provider)
        system_prompt = self.prompt_builder.build(agent=agent)
        tools = list(NATIVE_TOOLS)

        context: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        async for event in self._run_execution_loop(
            provider=provider,
            context=context,
            credentials=credentials,
            tools=tools,
            agent=agent,
            conversation=conversation,
            owner_email=owner_email,
            actor_id=actor_id,
            system_prompt=system_prompt,
        ):
            yield event

        full_response = self._extract_response_from_context(context)

        async for event in self._finalize_conversation(
            conversation_id=conversation.conversation_id,
            agent_id=agent.agent_id,
            actor_id=actor_id,
            owner_email=owner_email,
            actor_email=actor_email,
            full_response=full_response,
        ):
            yield event

    async def _run_execution_loop(
        self,
        provider: Any,
        context: list[dict[str, Any]],
        credentials: dict[str, Any],
        tools: list[dict[str, Any]],
        agent: "Agent",
        conversation: "Conversation",
        owner_email: str,
        actor_id: str,
        system_prompt: str,
    ) -> AsyncIterator[SSEEvent]:
        """Run the waterfall execution loop."""
        for loop_i in range(self.max_loops):
            runtime_ctx = self.event_context_builder.build(
                agent_id=agent.agent_id,
                conversation_id=conversation.conversation_id,
                actor_id=actor_id,
            )

            if runtime_ctx:
                context[0] = {
                    "role": "system",
                    "content": system_prompt + "\n\n" + runtime_ctx,
                }

            yield SSEEvent(
                event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                content=f"Planning next step... (loop {loop_i + 1}/{self.max_loops})",
            )

            tool_call_occurred = False

            async for event in self._process_llm_stream(
                provider=provider,
                context=context,
                credentials=credentials,
                tools=tools,
                agent=agent,
                conversation=conversation,
                owner_email=owner_email,
                actor_id=actor_id,
            ):
                yield event
                if event.event_type == SSEEventType.TOOL_CALL_RESULT:
                    tool_call_occurred = True

            if not tool_call_occurred:
                break

    async def _process_llm_stream(
        self,
        provider: Any,
        context: list[dict[str, Any]],
        credentials: dict[str, Any],
        tools: list[dict[str, Any]],
        agent: "Agent",
        conversation: "Conversation",
        owner_email: str,
        actor_id: str,
    ) -> AsyncIterator[SSEEvent]:
        """Process LLM stream and handle tool calls."""
        async for ev in provider.stream_response(
            messages=context,
            credentials=credentials,
            tools=tools,
            model=agent.agent_model,
        ):
            if ev.type == "text":
                yield SSEEvent(
                    event_type=SSEEventType.AGENT_RESPONSE_TO_USER,
                    content=ev.content,
                )

            elif ev.type == "tool_use":
                async for event in self._handle_tool_call(
                    ev=ev,
                    context=context,
                    agent_id=agent.agent_id,
                    conversation_id=conversation.conversation_id,
                    owner_email=owner_email,
                    actor_id=actor_id,
                ):
                    yield event

    async def _handle_tool_call(
        self,
        ev: Any,
        context: list[dict[str, Any]],
        agent_id: str,
        conversation_id: str,
        owner_email: str,
        actor_id: str,
    ) -> AsyncIterator[SSEEvent]:
        """Handle a single tool call: persist, execute, and add result to context."""
        tool_name = ev.tool_name
        tool_args = ev.tool_input or {}

        self.event_persister.append(
            agent_id=agent_id,
            conversation_id=conversation_id,
            actor_id=actor_id,
            owner_email=owner_email,
            event_type=RuntimeEventType.TOOL_CALL_REQUESTED,
            payload={"tool_name": tool_name, "tool_args": tool_args},
        )

        yield SSEEvent(
            event_type=SSEEventType.TOOL_CALL_START,
            content=f"Calling tool: {tool_name}",
            tool_name=tool_name,
            tool_args=tool_args,
        )

        context.append(
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": ev.tool_use_id,
                            "name": tool_name,
                            "input": tool_args,
                        }
                    }
                ],
            }
        )

        result, success = await self.tool_executor.execute(
            tool_name=tool_name,
            tool_args=tool_args,
            agent_id=agent_id,
        )

        self.event_persister.append(
            agent_id=agent_id,
            conversation_id=conversation_id,
            actor_id=actor_id,
            owner_email=owner_email,
            event_type=RuntimeEventType.TOOL_CALL_RESULT,
            payload={
                "tool_name": tool_name,
                "success": success,
                "result_preview": (result[:500] + "...") if len(result) > 500 else result,
            },
        )

        yield SSEEvent(
            event_type=SSEEventType.TOOL_CALL_RESULT,
            content=(result[:200] + "...") if len(result) > 200 else result,
            tool_name=tool_name,
            success=success,
        )

        context.append(
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": ev.tool_use_id,
                            "content": [{"text": result}],
                        }
                    }
                ],
            }
        )

    def _extract_response_from_context(self, context: list[dict[str, Any]]) -> str:
        """Extract assistant response text from context."""
        for msg in reversed(context):
            if msg.get("role") == "assistant":
                content = msg.get("content")
                if isinstance(content, str):
                    return content
        return ""

    def _initialize_context(self, conversation_id: str, actor_id: str) -> None:
        """Initialize tool handler context scoped per conversation and actor."""
        self.tool_handler.set_conversation_context(conversation_id)
        self.tool_handler.set_user_context(actor_id)

    def _save_user_message(
        self,
        conversation_id: str,
        actor_email: str,
        content: str,
        attachments: list[Attachment] | None = None,
    ) -> Message:
        """Save user message to repository."""
        msg = Message(
            conversation_id=conversation_id,
            created_by=actor_email,
            role="user",
            content=content,
            attachments=attachments or [],
        )
        self.message_repo.save(msg)
        return msg

    def _ensure_memory_initialized(self, agent_id: str, actor_id: str) -> None:
        """Ensure default memory blocks exist for agent and actor."""
        block_defs = self.memory_repo.get_block_definitions(agent_id, actor_id)
        if not block_defs:
            self.memory_repo.initialize_default_blocks(agent_id, actor_id)

    async def _finalize_conversation(
        self,
        conversation_id: str,
        agent_id: str,
        actor_id: str,
        owner_email: str,
        actor_email: str,
        full_response: str,
    ) -> AsyncIterator[SSEEvent]:
        """Save assistant message and emit completion events."""
        if full_response.strip():
            assistant_msg = Message(
                conversation_id=conversation_id,
                created_by=actor_email,
                role="assistant",
                content=full_response,
            )
            self.message_repo.save(assistant_msg)

            self.event_persister.append(
                agent_id=agent_id,
                conversation_id=conversation_id,
                actor_id=actor_id,
                owner_email=owner_email,
                event_type=RuntimeEventType.TURN_FINISHED,
                payload={"message_id": assistant_msg.message_id},
            )

            yield SSEEvent(
                event_type=SSEEventType.STREAM_COMPLETE,
                content="Response complete",
                message_id=assistant_msg.message_id,
            )
        else:
            self.event_persister.append(
                agent_id=agent_id,
                conversation_id=conversation_id,
                actor_id=actor_id,
                owner_email=owner_email,
                event_type=RuntimeEventType.TURN_FINISHED,
                payload={"message_id": None},
            )
            yield SSEEvent(
                event_type=SSEEventType.STREAM_COMPLETE,
                content="Response complete (tools only)",
            )
