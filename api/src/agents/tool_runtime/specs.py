"""What a tool is: a provider-facing definition plus how to run it."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel

from src.agents.runtime_state import AgentTurnState


class ToolCategory(str, Enum):
    """Decides whether a tool's definition is offered to the model this turn.

    An agent with no skills installed should not be told about skill tools.
    """

    NATIVE = "native"
    KNOWLEDGE = "knowledge"
    SKILL = "skill"
    MCP = "mcp"


#: Runs one tool call and returns the result text for the model.
ToolHandler = Callable[[str, dict[str, Any], AgentTurnState], Awaitable[str]]


@dataclass(frozen=True)
class ToolSpec:
    """A tool's declaration, independent of the runtime that will serve it."""

    definition: dict[str, Any]
    category: ToolCategory
    #: Validates and normalises the model's arguments. Also where an alias like
    #: `async` -> `async_` is applied, which the handlers rely on.
    input_model: type[BaseModel] | None = None
    #: True when running this tool can make the rendered system prompt stale.
    mutates_prompt_context: bool = False
    timeout_seconds: float | None = None

    @property
    def name(self) -> str:
        name = self.definition.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("Tool definition must include a non-empty string name")
        return name


@dataclass(frozen=True)
class ToolExecutionOutcome:
    result: str
    success: bool


@dataclass(frozen=True)
class BoundTool:
    """A spec bound to the handler that will run it."""

    spec: ToolSpec
    handler: ToolHandler

    @property
    def name(self) -> str:
        return self.spec.name

    async def run(self, tool_input: dict[str, Any], state: AgentTurnState) -> str:
        if self.spec.input_model is not None:
            tool_input = self.spec.input_model.model_validate(tool_input).model_dump(
                by_alias=True,
                exclude_none=True,
                exclude_unset=True,
            )
        return await self.handler(self.spec.name, tool_input, state)
