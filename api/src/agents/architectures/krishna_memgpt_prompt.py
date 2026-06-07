"""Prompt construction for Krishna MemGPT."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from src.agents.models import MemoryCapacityWarning
from src.connectors.mcp.models import AgentMCPConnectionResponse
from src.memory import MemoryRepository
from src.memory.snapshot import CoreMemorySnapshot
from src.skills.models import AgentSkill

PROMPT_TEMPLATE_DIR = Path(__file__).parents[1] / "prompt_templates"
SYSTEM_PROMPT_TEMPLATE = "krishna_memgpt_system_prompt.j2"

_env = Environment(
    loader=FileSystemLoader(PROMPT_TEMPLATE_DIR),
    undefined=StrictUndefined,
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


def build_krishna_memgpt_system_prompt(
    *,
    agent_persona: str,
    memory_repo: MemoryRepository,
    agent_id: str,
    user_id: str,
    kb_count: int | None = None,
    enabled_skills: list[AgentSkill] | None = None,
    enabled_mcp_connections: list[AgentMCPConnectionResponse] | None = None,
    core_memory: CoreMemorySnapshot | None = None,
    capacity_warnings: list[MemoryCapacityWarning] | None = None,
) -> str:
    # These are kept in the signature as a stable architecture seam. The
    # template renders from the snapshot already loaded by krishna_memgpt.py.
    del memory_repo, agent_id, user_id

    template = _env.get_template(SYSTEM_PROMPT_TEMPLATE)
    return template.render(
        timestamp=datetime.now(timezone.utc).strftime("%A, %B %d, %Y at %I:%M %p UTC"),
        agent_persona=agent_persona,
        core_memory=core_memory,
        kb_count=kb_count or 0,
        enabled_skills=enabled_skills or [],
        enabled_mcp_connections=enabled_mcp_connections or [],
        capacity_warnings=capacity_warnings or [],
    ).strip()
