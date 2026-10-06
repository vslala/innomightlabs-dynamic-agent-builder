"""Who is speaking in a turn, what they asked, and what the architecture loaded for them.

Provider credentials are not here: the provider session owns them, so a tool can never reach them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.messages.models import Attachment
from src.skills.models import ActorKind, AgentSkill, LoadedSkillRuntimeResponse

if TYPE_CHECKING:
    from src.connectors.mcp.models import AgentMCPConnectionResponse


@dataclass
class AgentTurnState:
    owner_email: str
    actor_email: str
    actor_id: str
    actor_kind: ActorKind
    conversation_id: str
    agent_id: str
    model_name: str

    user_message: str
    user_message_id: str | None = None
    attachments: list[Attachment] = field(default_factory=list)
    #: Public API secret key this turn runs under; token usage is also counted against it.
    api_key_id: str | None = None
    #: The conversation's standing context, rendered into every system prompt of the turn.
    conversation_context: str | None = None

    # Enrichment (populated during preflight)
    linked_kb_ids: list[str] = field(default_factory=list)
    enabled_skills: list[AgentSkill] = field(default_factory=list)
    #: Skill actions used recently in this conversation, whose schemas stay in the prompt.
    recent_skill_actions: list[LoadedSkillRuntimeResponse] = field(default_factory=list)
    enabled_mcp_connections: list["AgentMCPConnectionResponse"] = field(default_factory=list)
