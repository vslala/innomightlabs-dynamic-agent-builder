"""Tool families: when a set of tools is offered, and the instructions that come with it.

A family is offered when the conversation holds a reference of a kind it is triggered by (`Message.references`, see
`messages/references.py`), or when its own condition holds (a linked knowledge base). An architecture keeps its
families in one ordered list: the order is the order of their prompt sections. See
docs/LLD-message-references-and-tool-families.md.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.agents.runtime_state import AgentTurnState
from src.agents.tool_runtime.specs import ToolCategory


@dataclass(frozen=True)
class ToolFamily:
    category: ToolCategory
    #: Offered when the conversation holds a reference of any of these kinds...
    triggered_by: frozenset[str] = frozenset()
    #: ...or when this holds. A family with neither is never offered.
    when: Callable[[AgentTurnState], bool] | None = None
    #: Instructions rendered into the system prompt while the family is offered.
    prompt_section: Callable[[AgentTurnState], str] | None = None

    def active(self, state: AgentTurnState) -> bool:
        return any(state.references.get(kind) for kind in self.triggered_by) or bool(self.when and self.when(state))


def active_families(families: list[ToolFamily], state: AgentTurnState) -> list[ToolFamily]:
    return [family for family in families if family.active(state)]


def prompt_sections(families: list[ToolFamily], state: AgentTurnState) -> list[str]:
    """The sections of the families offered this turn, in order; a family that isn't offered adds nothing."""
    return [
        section
        for family in active_families(families, state)
        if family.prompt_section and (section := family.prompt_section(state))
    ]
