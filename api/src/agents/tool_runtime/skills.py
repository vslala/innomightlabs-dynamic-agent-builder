"""Skill runtime tool specs."""

from __future__ import annotations

from src.agents.tool_runtime.commands import (
    ToolCommandCategory,
    ToolCommandMetadata,
    ToolIdempotency,
    ToolSpec,
)


LOAD_SKILL_TOOL = {
    "name": "load_skill",
    "description": "Load full instructions and action contracts for an installed skill by skill_id.",
    "parameters": {
        "type": "object",
        "properties": {
            "skill_id": {"type": "string", "description": "Installed skill id to load"},
        },
        "required": ["skill_id"],
    },
}

EXECUTE_SKILL_ACTION_TOOL = {
    "name": "execute_skill_action",
    "description": (
        "Execute an action from an installed skill. "
        "IMPORTANT: pass action fields inside the `arguments` object only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "skill_id": {"type": "string", "description": "Installed skill id"},
            "action": {"type": "string", "description": "Action name defined by the skill"},
            "arguments": {
                "type": "object",
                "description": (
                    "Action arguments following the action input_schema. "
                    "Example: {\"query\": \"pricing\"}"
                ),
            },
        },
        "required": ["skill_id", "action", "arguments"],
        "additionalProperties": False,
    },
}

SKILL_TOOL_SPECS = [
    ToolSpec(
        LOAD_SKILL_TOOL,
        ToolCommandMetadata(
            category=ToolCommandCategory.SKILL,
            idempotency=ToolIdempotency.READ_ONLY,
            allow_parallel=True,
        ),
    ),
    ToolSpec(
        EXECUTE_SKILL_ACTION_TOOL,
        ToolCommandMetadata(
            category=ToolCommandCategory.SKILL,
            idempotency=ToolIdempotency.NON_IDEMPOTENT_WRITE,
        ),
    ),
]
