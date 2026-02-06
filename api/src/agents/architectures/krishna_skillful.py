"""Krishna Skillful Architecture.

Skillful = tool- and skill-driven architecture with a waterfall execution loop.

Key principles:
- Single entry-point `handle_message`.
- Each action emits:
  1) An SSE event (real-time UI)
  2) A RuntimeEvent persisted to DynamoDB (durable truth)
- Context for each loop iteration is rebuilt from persisted RuntimeEvents + memory.

Phase 1 scope:
- Implements the execution loop + durable runtime event logging.
- Provides only a minimal skill catalog (skills_list) + skill loader (skills_load).
- Memory tools are available by default (same as memgpt) and use the native tool handler.

Later phases will add:
- S3-backed skill registry + credentials
- Dynamic tool activation based on loaded skills
- HTTP GET/POST executor + marketplace skills
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

from src.agents.architectures.base import AgentArchitecture
from src.llm.events import SSEEvent, SSEEventType
from src.llm.providers.factory import get_llm_provider
from src.messages.models import Attachment, Message
from src.messages.repository import MessageRepository
from src.settings.repository import get_provider_settings_repository
from src.crypto import decrypt
from src.tools.native.definitions import NATIVE_TOOLS
from src.tools.native.handlers import NativeToolHandler

from src.runtime_events.models import RuntimeEvent, RuntimeEventType
from src.runtime_events.repository import RuntimeEventRepository

log = logging.getLogger(__name__)


# Skill tools exposed to the LLM (kept minimal; real tool definitions live in skills)
SKILLS_LIST_TOOL = {
    "name": "skills_list",
    "description": "List available skills (id + description). Use this to decide what to load.",
    "parameters": {"type": "object", "properties": {}},
}

SKILLS_LOAD_TOOL = {
    "name": "skills_load",
    "description": "Load a skill by skill_id so its tools can be used. Use skills_list first.",
    "parameters": {
        "type": "object",
        "properties": {
            "skill_id": {"type": "string", "description": "Skill identifier"},
        },
        "required": ["skill_id"],
    },
}


class KrishnaSkillfulArchitecture(AgentArchitecture):
    def __init__(self, max_context_words: int = 12000, max_loops: int = 8):
        self.max_context_words = max_context_words
        self.max_loops = max_loops

        self.message_repo = MessageRepository()
        self.provider_settings_repo = get_provider_settings_repository()
        self.tool_handler = NativeToolHandler()
        self.events_repo = RuntimeEventRepository()

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
        """Waterfall execution loop."""

        # Initialize tool handler context (memory scoped per actor_id)
        self.tool_handler.set_conversation_context(conversation.conversation_id)
        self.tool_handler.set_user_context(actor_id)

        # Persist turn started
        self._append_event(
            agent_id=agent.agent_id,
            conversation_id=conversation.conversation_id,
            actor_id=actor_id,
            owner_email=owner_email,
            event_type=RuntimeEventType.TURN_STARTED,
            payload={"actor_email": actor_email},
        )

        # 1) Save user message
        user_msg = Message(
            conversation_id=conversation.conversation_id,
            created_by=actor_email,
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

        # 2) Load provider credentials (tenant/owner scoped)
        yield SSEEvent(
            event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
            content="Loading provider configuration...",
        )

        provider_settings = self.provider_settings_repo.find_by_provider(owner_email, agent.agent_provider)
        if not provider_settings:
            yield SSEEvent(
                event_type=SSEEventType.ERROR,
                content=(
                    f"Provider '{agent.agent_provider}' is not configured for owner '{owner_email}'. "
                    "Please configure it in Settings > Provider Configuration."
                ),
            )
            return

        credentials = json.loads(decrypt(provider_settings.encrypted_credentials))

        provider = get_llm_provider(agent.agent_provider)

        # 3) Build base system prompt (Phase 1: minimal)
        system_prompt = self._build_system_prompt(agent=agent)

        # 4) Execution loop: plan -> (tool?) -> persist -> repeat
        tools = list(NATIVE_TOOLS) + [SKILLS_LIST_TOOL, SKILLS_LOAD_TOOL]

        context: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        full_response = ""

        for loop_i in range(self.max_loops):
            # Load persisted runtime event context (for determinism/debug)
            runtime_ctx = self._build_runtime_events_context(
                agent_id=agent.agent_id,
                conversation_id=conversation.conversation_id,
                actor_id=actor_id,
            )
            if runtime_ctx:
                # Keep it in-band as system note
                context[0] = {
                    "role": "system",
                    "content": system_prompt + "\n\n" + runtime_ctx,
                }

            yield SSEEvent(
                event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                content=f"Planning next step... (loop {loop_i + 1}/{self.max_loops})",
            )

            has_tool_calls = False

            async for ev in provider.stream_response(
                messages=context,
                credentials=credentials,
                tools=tools,
                model=agent.agent_model,
            ):
                if ev.type == "text":
                    full_response += ev.content
                    yield SSEEvent(
                        event_type=SSEEventType.AGENT_RESPONSE_TO_USER,
                        content=ev.content,
                    )

                elif ev.type == "tool_use":
                    has_tool_calls = True

                    tool_name = ev.tool_name
                    tool_args = ev.tool_input or {}

                    # Persist tool call requested
                    self._append_event(
                        agent_id=agent.agent_id,
                        conversation_id=conversation.conversation_id,
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

                    # Execute tool
                    result, success = await self._execute_tool(
                        tool_name=tool_name,
                        tool_args=tool_args,
                        agent_id=agent.agent_id,
                        owner_email=owner_email,
                        actor_id=actor_id,
                        conversation_id=conversation.conversation_id,
                    )

                    # Persist tool result
                    self._append_event(
                        agent_id=agent.agent_id,
                        conversation_id=conversation.conversation_id,
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

                    # Feed tool result back to LLM in Bedrock toolResult format
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

                elif ev.type == "stop":
                    pass

            if not has_tool_calls:
                break

        # Save assistant message
        if full_response.strip():
            assistant_msg = Message(
                conversation_id=conversation.conversation_id,
                created_by=actor_email,
                role="assistant",
                content=full_response,
            )
            self.message_repo.save(assistant_msg)

            self._append_event(
                agent_id=agent.agent_id,
                conversation_id=conversation.conversation_id,
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
            self._append_event(
                agent_id=agent.agent_id,
                conversation_id=conversation.conversation_id,
                actor_id=actor_id,
                owner_email=owner_email,
                event_type=RuntimeEventType.TURN_FINISHED,
                payload={"message_id": None},
            )
            yield SSEEvent(
                event_type=SSEEventType.STREAM_COMPLETE,
                content="Response complete (tools only)",
            )

    async def _execute_tool(
        self,
        tool_name: str,
        tool_args: dict,
        agent_id: str,
        owner_email: str,
        actor_id: str,
        conversation_id: str,
    ) -> tuple[str, bool]:
        """Execute a tool. Phase 1 supports memory tools + skills_list/load."""
        try:
            if tool_name == "skills_list":
                self._append_event(
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    actor_id=actor_id,
                    owner_email=owner_email,
                    event_type=RuntimeEventType.SKILLS_LIST_SHOWN,
                    payload={},
                )
                # Phase 1: static catalog stub
                return (
                    "Available skills (Phase 1 stub):\n"
                    "- native.http_get_post: Perform safe HTTP GET/POST requests (coming next phase)\n"
                    "- native.wordpress: Search/get posts via WordPress REST API (future)\n"
                    "Use skills_load({skill_id}) to load a skill.",
                    True,
                )

            if tool_name == "skills_load":
                skill_id = str(tool_args.get("skill_id", "")).strip()
                if not skill_id:
                    return "Error: missing skill_id", False

                self._append_event(
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    actor_id=actor_id,
                    owner_email=owner_email,
                    event_type=RuntimeEventType.SKILL_LOADED,
                    payload={"skill_id": skill_id},
                )
                return (
                    f"Loaded skill '{skill_id}' (Phase 1 stub). "
                    "In next phase, this will activate the skill tools for use.",
                    True,
                )

            # Delegate native memory/KB tools
            result = await self.tool_handler.execute(tool_name, tool_args, agent_id)
            return result, True

        except Exception as e:
            log.error(f"Tool execution error ({tool_name}): {e}", exc_info=True)
            return f"Error: {str(e)}", False

    def _append_event(
        self,
        agent_id: str,
        conversation_id: str,
        actor_id: str,
        owner_email: str,
        event_type: RuntimeEventType,
        payload: dict[str, Any],
    ) -> None:
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
            # Don’t break the agent run for event logging failures
            log.error(f"Failed to append runtime event {event_type}: {e}", exc_info=True)

    def _build_runtime_events_context(self, agent_id: str, conversation_id: str, actor_id: str) -> str:
        """Summarize recent runtime events into a small system snippet."""
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

        # Only keep the highest-signal items
        lines: list[str] = ["<runtime_events>"]
        for ev in page.items[:10]:
            if ev.event_type in {RuntimeEventType.SKILL_LOADED, RuntimeEventType.TOOL_CALL_RESULT}:
                lines.append(f"- {ev.event_type.value}: {json.dumps(ev.payload, ensure_ascii=False)}")
        lines.append("</runtime_events>")
        return "\n".join(lines)

    def _build_system_prompt(self, agent: "Agent") -> str:
        return (
            "<identity>\n"
            "You are Krishna Skillful: an AI agent that can load and use skills on-demand.\n"
            "You MUST keep context lean: list skills first, load only what you need.\n"
            "</identity>\n\n"
            f"<persona>\n{agent.agent_persona}\n</persona>\n\n"
            "<skills_usage>\n"
            "- Use skills_list to see available skills (id + description).\n"
            "- Use skills_load(skill_id) to load a skill before using its tools.\n"
            "- Prefer memory tools to store stable facts.\n"
            "</skills_usage>"
        )
