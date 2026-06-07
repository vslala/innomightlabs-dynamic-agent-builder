"""Per-turn runtime state for agent architectures.

Keep this small and pragmatic. The goal is to:
- centralize shared inputs (kb_ids, enabled_skills, credentials, tools)
- reduce long parameter lists and cross-cutting concerns

We'll evolve this incrementally as we extract prompt building + tool execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.messages.models import Attachment
from src.skills.models import AgentSkill

if TYPE_CHECKING:
    from src.connectors.mcp.models import AgentMCPConnectionResponse


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
    enabled_skills: list[AgentSkill] = field(default_factory=list)
    enabled_mcp_connections: list["AgentMCPConnectionResponse"] = field(default_factory=list)

    # Provider runtime
    credentials: dict[str, Any] | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)

    # When a tool mutates core memory, we should rebuild the system prompt so the
    # model doesn't operate on stale memory context.
    prompt_dirty: bool = False
