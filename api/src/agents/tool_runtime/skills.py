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
        "IMPORTANT: pass action fields inside the `arguments` object only. "
        "For long-running actions, set async to true."
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
            "async": {
                "type": "boolean",
                "description": "Set true for long-running actions so the runtime can wait and check job status.",
            },
        },
        "required": ["skill_id", "action", "arguments"],
        "additionalProperties": False,
    },
}

CHECK_TOOL_JOB_TOOL = {
    "name": "check_tool_job",
    "description": "Check the status and result of an asynchronous tool job.",
    "parameters": {
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "Async tool job id"},
        },
        "required": ["job_id"],
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
    ToolSpec(
        CHECK_TOOL_JOB_TOOL,
        ToolCommandMetadata(
            category=ToolCommandCategory.SKILL,
            idempotency=ToolIdempotency.READ_ONLY,
        ),
    ),
]
