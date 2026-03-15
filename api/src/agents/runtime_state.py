"""Per-turn runtime state for agent architectures.

Keep this small and pragmatic. The goal is to:
- centralize shared inputs (kb_ids, enabled_skills, credentials, tools)
- reduce long parameter lists and cross-cutting concerns

We'll evolve this incrementally as we extract prompt building + tool execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.messages.models import Attachment


@dataclass
class AgentTurnState:
    owner_email: str
    actor_email: str
    actor_id: str
    conversation_id: str
    agent_id: str
    provider_name: str
    model_name: str

    user_message: str
    attachments: list[Attachment] = field(default_factory=list)

    # Enrichment (populated during preflight)
    linked_kb_ids: list[str] = field(default_factory=list)
    enabled_skills: list[dict[str, Any]] = field(default_factory=list)

    # Provider runtime
    credentials: dict[str, Any] | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)
