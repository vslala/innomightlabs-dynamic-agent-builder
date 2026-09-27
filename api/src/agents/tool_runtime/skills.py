"""Skill runtime tool specs."""

from __future__ import annotations

from src.agents.tool_runtime.skill_contracts import (
    CheckToolJobInput,
    ExecuteSkillActionInput,
    LoadSkillInput,
)
from src.agents.tool_runtime.specs import ToolCategory, ToolSpec


LOAD_SKILL_TOOL = {
    "name": "load_skill",
    "description": (
        "Load an installed skill's instructions and action contracts. "
        "Large skills return an action_index of names and summaries instead of schemas; "
        "then pass `actions` with the names you need, or `query` to search, to get their full schemas."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "skill_id": {"type": "string", "description": "Installed skill id to load"},
            "actions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Action names to load full schemas for.",
            },
            "query": {
                "type": "string",
                "description": "Words describing the task, e.g. 'negative keywords'. Returns the matching actions.",
            },
        },
        "required": ["skill_id"],
        "additionalProperties": False,
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
    ToolSpec(LOAD_SKILL_TOOL, ToolCategory.SKILL, LoadSkillInput),
    ToolSpec(EXECUTE_SKILL_ACTION_TOOL, ToolCategory.SKILL, ExecuteSkillActionInput),
    ToolSpec(CHECK_TOOL_JOB_TOOL, ToolCategory.SKILL, CheckToolJobInput),
]
