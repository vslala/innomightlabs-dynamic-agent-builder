"""Strict-JSON LLM planner for Dream transcript chunks."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from pydantic import ValidationError

from src.dream.models import DreamPlan
from src.dream.sessions import DreamSessionChunk
from src.llm.providers.base import LLMProvider
from src.memory.models import CoreMemory, MemoryBlockDefinition
from src.smart_suggestions.strategies import _extract_json_object

# The model responded but the content didn't parse into a valid plan -- often a one-off
# sampling glitch on weaker/local models rather than something a fresh call won't fix.
# A stall (dead connection, no data at all) raises TimeoutError instead, which is not
# retried here: session atomicity already accepts a whole-session retry for that case.
MAX_PARSE_ATTEMPTS = 3

SYSTEM_PROMPT = """You are the dreaming subconscious of an AI agent reviewing a closed conversation session.
Return ONLY JSON with this exact shape: {\"actions\":[...],\"session_summary\":\"string\"}.
Each action has type, block_name, line_number, content, reason, confidence. Valid types are append_core,
replace_core, delete_core, insert_archival, no_op. Remember only durable user facts, preferences,
constraints, recurring context, and corrections. Never remember secrets, credentials, one-off instructions,
or guesses. Prefer replacing or deleting contradictory memory. Use confidence below 0.75 when uncertain."""


@dataclass(frozen=True)
class DreamPlanningResult:
    plan: DreamPlan
    prompt_tokens: int
    completion_tokens: int


class DreamPlanner:
    async def plan(
        self,
        *,
        provider: LLMProvider,
        credentials: dict,
        model_name: str,
        chunk: DreamSessionChunk,
        block_definitions: list[MemoryBlockDefinition],
        core_memories: list[CoreMemory],
        prior_summary: str = "",
        stall_timeout_seconds: float = 150,
    ) -> DreamPlanningResult:
        payload = {
            "session": {
                "conversation_id": chunk.session.conversation_id,
                "started_at": chunk.session.started_at.isoformat(),
                "ended_at": chunk.session.ended_at.isoformat(),
                "chunk": {"index": chunk.index + 1, "total": chunk.total, "granularity": chunk.granularity},
            },
            "prior_summary": prior_summary,
            "blocks": [
                {"name": block.block_name, "description": block.description, "word_limit": block.word_limit}
                for block in block_definitions
            ],
            "core_memory": [
                {"block_name": memory.block_name, "lines": list(enumerate(memory.lines, start=1))}
                for memory in core_memories
            ],
            "transcript": [
                {
                    "role": message.role,
                    "content": message.content,
                    "attachments": [attachment.filename for attachment in message.attachments],
                    "images": "[image]" if message.images else "",
                    "canvases": "[canvas]" if message.canvases else "",
                }
                for message in chunk.messages
            ],
        }
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
        ]
        last_error: ValueError | ValidationError = ValueError("Dream planner returned an empty response")
        for _attempt in range(MAX_PARSE_ATTEMPTS):
            try:
                return await self._stream_once(provider, credentials, model_name, messages, stall_timeout_seconds)
            except (ValueError, ValidationError) as exc:
                last_error = exc
        raise last_error

    async def _stream_once(
        self,
        provider: LLMProvider,
        credentials: dict,
        model_name: str,
        messages: list[dict],
        stall_timeout_seconds: float,
    ) -> DreamPlanningResult:
        response = ""
        prompt_tokens = completion_tokens = 0
        events = provider.stream_response(messages, credentials, tools=None, model=model_name)
        while True:
            try:
                # A stall timeout, not a call timeout: it resets on every event, so a response
                # that keeps actively streaming can run as long as it needs to. Only a provider
                # that goes quiet mid-stream (connection kept open, nothing arriving) trips it.
                event = await asyncio.wait_for(events.__anext__(), timeout=stall_timeout_seconds)
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError as exc:
                raise TimeoutError(
                    f"Dream planner received no data for {stall_timeout_seconds} seconds"
                ) from exc
            if event.type == "text":
                response += event.content
            elif event.type == "usage":
                prompt_tokens += event.prompt_tokens
                completion_tokens += event.completion_tokens
        if not response.strip():
            raise ValueError("Dream planner returned an empty response")
        return DreamPlanningResult(
            plan=DreamPlan.model_validate_json(_extract_json_object(response)),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
