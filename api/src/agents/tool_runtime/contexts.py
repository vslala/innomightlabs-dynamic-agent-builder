"""Typed context resolution for tool commands."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from src.agents.runtime_state import AgentTurnState

T = TypeVar("T")


class MissingToolContextError(ValueError):
    pass


@dataclass(frozen=True)
class ToolExecutionContext:
    owner_email: str
    actor_email: str
    actor_id: str
    agent_id: str
    conversation_id: str
    user_message_id: str | None = None


@dataclass(frozen=True)
class NativeToolContext:
    agent_id: str
    user_id: str
    conversation_id: str
    linked_kb_ids: list[str]


@dataclass(frozen=True)
class SkillToolContext:
    agent_id: str
    owner_email: str
    actor_email: str
    actor_id: str
    conversation_id: str
    user_message_id: str | None = None


@dataclass(frozen=True)
class MCPToolContext:
    owner_email: str
    agent_id: str


class ToolContextResolver:
    def __init__(self):
        self._factories: dict[type[object], Callable[[], object]] = {}

    def register(self, context_type: type[T], factory: Callable[[], T]) -> None:
        self._factories[context_type] = factory

    def resolve(self, context_type: type[T]) -> T:
        factory = self._factories.get(context_type)
        if factory is None:
            raise MissingToolContextError(f"Missing tool context: {context_type.__name__}")
        return factory()


def build_tool_context_resolver(state: AgentTurnState) -> ToolContextResolver:
    resolver = ToolContextResolver()
    resolver.register(
        ToolExecutionContext,
        lambda: ToolExecutionContext(
            owner_email=state.owner_email,
            actor_email=state.actor_email,
            actor_id=state.actor_id,
            agent_id=state.agent_id,
            conversation_id=state.conversation_id,
            user_message_id=state.user_message_id,
        ),
    )
    resolver.register(
        NativeToolContext,
        lambda: NativeToolContext(
            agent_id=state.agent_id,
            user_id=state.actor_id,
            conversation_id=state.conversation_id,
            linked_kb_ids=list(state.linked_kb_ids),
        ),
    )
    resolver.register(
        SkillToolContext,
        lambda: SkillToolContext(
            agent_id=state.agent_id,
            owner_email=state.owner_email,
            actor_email=state.actor_email,
            actor_id=state.actor_id,
            conversation_id=state.conversation_id,
            user_message_id=state.user_message_id,
        ),
    )
    resolver.register(
        MCPToolContext,
        lambda: MCPToolContext(
            owner_email=state.owner_email,
            agent_id=state.agent_id,
        ),
    )
    return resolver
