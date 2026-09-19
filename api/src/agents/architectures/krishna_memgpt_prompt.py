"""Prompt construction for Krishna MemGPT."""

from __future__ import annotations

from src.agents.models import MemoryCapacityWarning
from src.agents.prompts import render_system_prompt
from src.connectors.mcp.models import AgentMCPConnectionResponse
from src.memory.snapshot import CoreMemorySnapshot
from src.skills.models import AgentSkill

SYSTEM_PROMPT_TEMPLATE = "krishna_memgpt_system_prompt.j2"


def build_krishna_memgpt_system_prompt(
    *,
    agent_persona: str,
    kb_count: int | None = None,
    enabled_skills: list[AgentSkill] | None = None,
    enabled_mcp_connections: list[AgentMCPConnectionResponse] | None = None,
    core_memory: CoreMemorySnapshot | None = None,
    capacity_warnings: list[MemoryCapacityWarning] | None = None,
) -> str:
    return render_system_prompt(
        SYSTEM_PROMPT_TEMPLATE,
        has_memory_tools=True,
        agent_persona=agent_persona,
        core_memory=core_memory,
        kb_count=kb_count or 0,
        enabled_skills=enabled_skills or [],
        enabled_mcp_connections=enabled_mcp_connections or [],
        capacity_warnings=capacity_warnings or [],
    )
