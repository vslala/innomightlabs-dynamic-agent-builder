"""Strict-JSON LLM planner for Dream transcript chunks."""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.dream.models import DreamPlan
from src.dream.sessions import DreamSessionChunk
from src.llm.providers.base import LLMProvider
from src.memory.models import CoreMemory, MemoryBlockDefinition
from src.smart_suggestions.strategies import _extract_json_object

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
        response = ""
        prompt_tokens = completion_tokens = 0
        async for event in provider.stream_response(
            [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": json.dumps(payload)}],
            credentials,
            tools=None,
            model=model_name,
        ):
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
