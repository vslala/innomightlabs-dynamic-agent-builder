"""Prompt construction for Vishwakarma, the architecture behind Ada the solution builder."""

from __future__ import annotations

from typing import Any

from src.agents.prompts import render_system_prompt
from src.blueprints.catalog import BuildIdea
from src.builder.models import BuilderSession

SYSTEM_PROMPT_TEMPLATE = "vishwakarma_system_prompt.j2"


def build_vishwakarma_system_prompt(
    *,
    ideas: list[BuildIdea],
    catalog: dict[str, Any],
    session: BuilderSession,
    conversation_context: str | None = None,
) -> str:
    """Renders data already loaded for this turn: the ideas, the blueprint language, and the current draft."""
    return render_system_prompt(
        SYSTEM_PROMPT_TEMPLATE,
        has_memory_tools=False,
        conversation_context=conversation_context,
        ideas=ideas,
        kinds=catalog["kinds"],
        skills=catalog["skills"],
        provider=session.provider,
        model=session.model,
        draft_yaml=session.draft_yaml,
        draft_params=session.draft_params,
        plan_id=session.plan_id,
        built=bool(session.deployment_id),
    )
