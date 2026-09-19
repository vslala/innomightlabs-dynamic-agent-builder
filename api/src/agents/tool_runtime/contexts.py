"""The slice of turn state each tool family needs.

Each context is built straight from `AgentTurnState` at the call site, so a
handler cannot reach for turn data it did not declare.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.agents.runtime_state import AgentTurnState


@dataclass(frozen=True)
class NativeToolContext:
    agent_id: str
    user_id: str
    conversation_id: str
    linked_kb_ids: list[str]

    @classmethod
    def of(cls, state: AgentTurnState) -> "NativeToolContext":
        return cls(
            agent_id=state.agent_id,
            user_id=state.actor_id,
            conversation_id=state.conversation_id,
            linked_kb_ids=list(state.linked_kb_ids),
        )


@dataclass(frozen=True)
class SkillToolContext:
    agent_id: str
    owner_email: str
    actor_email: str
    actor_id: str
    conversation_id: str
    user_message_id: str | None = None

    @classmethod
    def of(cls, state: AgentTurnState) -> "SkillToolContext":
        return cls(
            agent_id=state.agent_id,
            owner_email=state.owner_email,
            actor_email=state.actor_email,
            actor_id=state.actor_id,
            conversation_id=state.conversation_id,
            user_message_id=state.user_message_id,
        )


@dataclass(frozen=True)
class MCPToolContext:
    owner_email: str
    agent_id: str

    @classmethod
    def of(cls, state: AgentTurnState) -> "MCPToolContext":
        return cls(owner_email=state.owner_email, agent_id=state.agent_id)
