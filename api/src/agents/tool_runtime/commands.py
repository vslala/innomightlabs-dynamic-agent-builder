"""Command abstractions for agent tool execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from src.agents.runtime_state import AgentTurnState


class ToolCommandCategory(str, Enum):
    NATIVE = "native"
    KNOWLEDGE = "knowledge"
    SKILL = "skill"
    MCP = "mcp"


class ToolIdempotency(str, Enum):
    READ_ONLY = "read_only"
    IDEMPOTENT_WRITE = "idempotent_write"
    NON_IDEMPOTENT_WRITE = "non_idempotent_write"


@dataclass(frozen=True)
class ToolCommandMetadata:
    category: ToolCommandCategory
    idempotency: ToolIdempotency
    mutates_prompt_context: bool = False
    timeout_seconds: int | None = None
    allow_parallel: bool = False


@dataclass(frozen=True)
class ToolSpec:
    """Provider-facing tool definition plus execution metadata."""

    definition: dict[str, Any]
    metadata: ToolCommandMetadata

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
        result = await self._executor.execute(
            request.tool_name,
            request.tool_input,
            request.state,
        )
        return ToolExecutionOutcome(result=result, success=True)
