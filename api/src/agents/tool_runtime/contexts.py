"""The slice of turn state a native tool may read.

Built straight from `AgentTurnState` at the call site, so a native handler
cannot reach for turn data it did not declare.
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
