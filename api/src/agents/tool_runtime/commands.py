"""Command abstractions for agent tool execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel

from src.agents.runtime_state import AgentTurnState
from src.agents.tool_runtime.contexts import ToolContextResolver


class ToolCommandCategory(str, Enum):
    NATIVE = "native"
    KNOWLEDGE = "knowledge"
    SKILL = "skill"
    MCP = "mcp"


@dataclass(frozen=True)
class ToolCommandMetadata:
    category: ToolCommandCategory
    mutates_prompt_context: bool = False
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class ToolSpec:
    """Provider-facing tool definition plus execution metadata."""

    definition: dict[str, Any]
    metadata: ToolCommandMetadata
    input_model: type[BaseModel] | None = None
    context_type: type[Any] | None = None

    @property
    def name(self) -> str:
        name = self.definition.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("Tool definition must include a non-empty string name")
        return name


@dataclass(frozen=True)
class ToolCommandRequest:
    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str
    state: AgentTurnState
    context_resolver: ToolContextResolver

    def parse_input(self, model_type: type[BaseModel]) -> BaseModel:
        return model_type.model_validate(self.tool_input)

    def resolve_context(self, context_type: type[Any]) -> Any:
        return self.context_resolver.resolve(context_type)


@dataclass(frozen=True)
class ToolExecutionOutcome:
    result: str
    success: bool


class ToolExecutor(Protocol):
    async def execute(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        state: AgentTurnState,
        context: Any | None = None,
    ) -> str:
        ...


class ToolCommand(Protocol):
    @property
    def name(self) -> str:
        ...

    @property
    def definition(self) -> dict[str, Any]:
        ...

    @property
    def metadata(self) -> ToolCommandMetadata:
        ...

    async def execute(self, request: ToolCommandRequest) -> ToolExecutionOutcome:
        ...


class ExecutorToolCommand:
    """Generic command for tools backed by a uniform executor adapter."""

    def __init__(
        self,
        *,
        spec: ToolSpec,
        executor: ToolExecutor,
    ):
        self._spec = spec
        self._executor = executor

    @property
    def name(self) -> str:
        return self._spec.name

    @property
    def definition(self) -> dict[str, Any]:
        return self._spec.definition

    @property
    def metadata(self) -> ToolCommandMetadata:
        return self._spec.metadata

    async def execute(self, request: ToolCommandRequest) -> ToolExecutionOutcome:
        tool_input = request.tool_input
        if self._spec.input_model is not None:
            parsed_input = request.parse_input(self._spec.input_model)
            tool_input = parsed_input.model_dump(
                by_alias=True,
                exclude_none=True,
                exclude_unset=True,
            )

        context = None
        if self._spec.context_type is not None:
            context = request.resolve_context(self._spec.context_type)

        result = await self._executor.execute(
            request.tool_name,
            tool_input,
            request.state,
            context=context,
        )
        return ToolExecutionOutcome(result=result, success=True)
