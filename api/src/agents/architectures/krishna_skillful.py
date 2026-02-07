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
from src.skills.repository import SkillsRepository
from src.skills.store import get_skills_store
from src.skills.tool_runtime import SkillToolRuntime

from src.runtime_events.models import RuntimeEvent, RuntimeEventType
from src.runtime_events.repository import RuntimeEventRepository
from src.memory.repository import MemoryRepository
from src.memory.models import MemoryBlockDefinition, EvictionPolicy, CoreMemory
from src.memory.eviction import MemoryEvictionService

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
        self.memory_repo = MemoryRepository()
        self.memory_eviction = MemoryEvictionService()

        self.skills_repo = SkillsRepository()
        self.skills_runtime = SkillToolRuntime(repo=self.skills_repo, store=get_skills_store())

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

        # Ensure default memory blocks exist + initialize loaded skills block
        self._ensure_memory_initialized(agent_id=agent.agent_id, actor_id=actor_id)
        self._ensure_loaded_skills_block(agent_id=agent.agent_id, actor_id=actor_id)

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
        # Tool catalog: native tools + skills_list/load + tools from loaded skill manifests
        loaded_skill_records = self._get_loaded_skill_records(agent_id=agent.agent_id, actor_id=actor_id)
        skill_tools = self._build_skill_tools(owner_email=owner_email, loaded_skill_records=loaded_skill_records)

        tools = list(NATIVE_TOOLS) + [SKILLS_LIST_TOOL, SKILLS_LOAD_TOOL] + skill_tools

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

            # Refresh skill tools each loop in case skills_load was called
            loaded_skill_records = self._get_loaded_skill_records(agent_id=agent.agent_id, actor_id=actor_id)
            skill_tools = self._build_skill_tools(owner_email=owner_email, loaded_skill_records=loaded_skill_records)
            tools = list(NATIVE_TOOLS) + [SKILLS_LIST_TOOL, SKILLS_LOAD_TOOL] + skill_tools

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

                    # IMPORTANT (Bedrock Converse protocol):
                    # When the model emits a toolUse block, the next turn must include:
                    # 1) an assistant message containing the toolUse block(s)
                    # 2) a user message containing the matching toolResult block(s)
                    # If we omit (1), Bedrock raises:
                    # "toolResult blocks ... exceeds ... toolUse blocks of previous turn".
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

                active = self.skills_repo.list_active(owner_email)
                if not active:
                    return "No active skills found. Upload a skill and activate it first.", True

                lines = ["Active skills:"]
                for s in active:
                    lines.append(f"- {s.skill_id}@{s.version}: {s.description or s.name}")
                lines.append("Use skills_load({skill_id}) to load a skill for tool use in this conversation.")
                return "\n".join(lines), True

            if tool_name == "skills_load":
                skill_id = str(tool_args.get("skill_id", "")).strip()
                if not skill_id:
                    return "Error: missing skill_id", False

                # Resolve an active skill version (MVP: first active match)
                active = [s for s in self.skills_repo.list_active(owner_email) if s.skill_id == skill_id]
                if not active:
                    return f"Error: skill '{skill_id}' not found or not active", False

                skill = active[0]

                # Load manifest to extract tool names/allowed hosts
                manifest = self.skills_runtime.load_manifest_for_skill(skill)
                tool_names = [t.get("name") for t in (manifest.tools or []) if isinstance(t, dict) and t.get("name")]

                # Persist durable event
                self._append_event(
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    actor_id=actor_id,
                    owner_email=owner_email,
                    event_type=RuntimeEventType.SKILL_LOADED,
                    payload={"skill_id": skill.skill_id, "version": skill.version, "tool_count": len(tool_names)},
                )

                # Update [loaded_skills] core memory with a compact record (LRU block)
                self._upsert_loaded_skill_record(
                    agent_id=agent_id,
                    actor_id=actor_id,
                    skill_id=skill.skill_id,
                    version=skill.version,
                    tools=tool_names,
                    allowed_hosts=manifest.allowed_hosts,
                    manifest_key=skill.s3_manifest_key,
                    skill_md_key=skill.s3_skill_md_key,
                )

                return (
                    f"Loaded skill '{skill.skill_id}@{skill.version}'. "
                    f"Tools now available: {', '.join(tool_names) if tool_names else '(none)'}.",
                    True,
                )

            # Delegate native tools first
            try:
                result = await self.tool_handler.execute(tool_name, tool_args, agent_id)
                return result, True
            except ValueError:
                # Not a native tool, try skill-defined tool dispatch
                loaded_skill_records = self._get_loaded_skill_records(agent_id=agent_id, actor_id=actor_id)
                resolved = self.skills_runtime.resolve_loaded_tool(
                    owner_email=owner_email,
                    loaded_skills=loaded_skill_records,
                    tool_name=tool_name,
                )
                if not resolved:
                    raise

                result = await self.skills_runtime.execute_tool(resolved, tool_args)
                return result, True

        except Exception as e:
            log.error(f"Tool execution error ({tool_name}): {e}", exc_info=True)
            return f"Error: {str(e)}", False

    def _get_loaded_skill_records(self, agent_id: str, actor_id: str) -> list[dict[str, Any]]:
        memory = self.memory_repo.get_core_memory(agent_id, actor_id, "loaded_skills")
        if not memory or not memory.lines:
            return []

        out: list[dict[str, Any]] = []
        for line in memory.lines:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                out.append(obj)
        return out

    def _build_skill_tools(self, owner_email: str, loaded_skill_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for rec in loaded_skill_records:
            skill_id = str(rec.get("skill_id", "") or "").strip()
            version = str(rec.get("version", "") or "").strip()
            if not skill_id or not version:
                continue
            skill = self.skills_repo.get(owner_email, skill_id, version)
            if not skill:
                continue
            try:
                manifest = self.skills_runtime.load_manifest_for_skill(skill)
            except Exception:
                continue
            tools.extend(self.skills_runtime.build_llm_tools_for_skill(manifest))
        return tools

    def _upsert_loaded_skill_record(
        self,
        agent_id: str,
        actor_id: str,
        skill_id: str,
        *,
        version: str,
        tools: list[str],
        allowed_hosts: list[str],
        manifest_key: str,
        skill_md_key: str,
    ) -> None:
        """Upsert a compact loaded skill record into core memory block [loaded_skills].

        Stored as a single JSON line per skill_id for deterministic parsing.
        Applies the block's eviction policy after update.
        """
        now = datetime.now(timezone.utc)

        block_def = self.memory_repo.get_block_definition(agent_id, actor_id, "loaded_skills")
        if not block_def:
            # Should exist via init, but keep it safe
            self._ensure_loaded_skills_block(agent_id, actor_id)
            block_def = self.memory_repo.get_block_definition(agent_id, actor_id, "loaded_skills")

        memory = self.memory_repo.get_core_memory(agent_id, actor_id, "loaded_skills")
        if not memory:
            memory = CoreMemory(agent_id=agent_id, user_id=actor_id, block_name="loaded_skills")

        memory.ensure_line_meta(now=now)

        # Parse existing lines and replace if skill_id exists
        new_line_obj = {
            "skill_id": skill_id,
            "version": version,
            "tools": tools,
            "allowed_hosts": allowed_hosts,
            "manifest_key": manifest_key,
            "skill_md_key": skill_md_key,
            "last_used_at": now.isoformat(),
        }
        new_line = json.dumps(new_line_obj, ensure_ascii=False)

        replaced = False
        for i, line in enumerate(list(memory.lines)):
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get("skill_id") == skill_id:
                memory.lines[i] = new_line
                if i < len(memory.line_meta):
                    memory.line_meta[i].last_accessed_at = now
                replaced = True
                break

        if not replaced:
            memory.lines.append(new_line)
            memory.ensure_line_meta(now=now)
            if memory.line_meta:
                memory.line_meta[-1].last_accessed_at = now

        # Apply eviction strategy (LRU) if needed
        assert block_def is not None
        self.memory_eviction.apply_if_needed(memory=memory, block_def=block_def, now=now)

        self.memory_repo.save_core_memory(memory)

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

    def _ensure_memory_initialized(self, agent_id: str, actor_id: str) -> None:
        """Ensure default memory blocks exist for this agent+actor."""
        block_defs = self.memory_repo.get_block_definitions(agent_id, actor_id)
        if not block_defs:
            self.memory_repo.initialize_default_blocks(agent_id, actor_id)

    def _ensure_loaded_skills_block(self, agent_id: str, actor_id: str) -> None:
        """Ensure the per-actor loaded_skills core memory block exists.

        This block is LRU-evicted so the agent can load skills without bloating context.
        """
        existing = self.memory_repo.get_block_definition(agent_id, actor_id, "loaded_skills")
        if not existing:
            block_def = MemoryBlockDefinition(
                agent_id=agent_id,
                user_id=actor_id,
                block_name="loaded_skills",
                description="Skills loaded for this conversation/user (LRU)",
                word_limit=2500,
                eviction_policy=EvictionPolicy.LRU,
                is_default=True,
            )
            self.memory_repo.save_block_definition(block_def)

        core = self.memory_repo.get_core_memory(agent_id, actor_id, "loaded_skills")
        if not core:
            self.memory_repo.save_core_memory(
                CoreMemory(agent_id=agent_id, user_id=actor_id, block_name="loaded_skills")
            )

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
            "- Loaded skills are tracked in your [loaded_skills] memory block.\n"
            "- Prefer memory tools to store stable facts.\n"
            "</skills_usage>"
        )
