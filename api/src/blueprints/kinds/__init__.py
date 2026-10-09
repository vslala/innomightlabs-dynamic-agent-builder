"""Every resource kind a blueprint can use. Adding a capability means adding a kind here, with its spec model;
the blueprint document's `resources` are read from this list (see `blueprints/document.py`)."""

from src.blueprints.kinds.agent import AgentKind
from src.blueprints.kinds.base import (
    Action,
    AppliedResource,
    ApplyContext,
    Change,
    Existing,
    LookupKind,
    ManagedKind,
    NotFound,
    PlanContext,
    ResourceKind,
    Usage,
)
from src.blueprints.kinds.knowledge_base import KnowledgeBaseKind
from src.blueprints.kinds.mcp_connection import McpConnectionKind
from src.blueprints.kinds.widget_key import WidgetKeyKind

RESOURCE_KINDS: tuple[ResourceKind, ...] = (KnowledgeBaseKind(), McpConnectionKind(), AgentKind(), WidgetKeyKind())

KIND_NAMES: list[str] = [kind.kind for kind in RESOURCE_KINDS]


def kind_for(name: str) -> ResourceKind:
    return next(kind for kind in RESOURCE_KINDS if kind.kind == name)


def managed_kind_for(name: str) -> ManagedKind:
    """The kind, for creating, changing or deleting one. Only managed kinds are ever planned that way."""
    kind = kind_for(name)
    if not isinstance(kind, ManagedKind):
        raise TypeError(f"A blueprint never creates, changes or deletes a {kind.label}.")
    return kind


__all__ = [
    "Action",
    "AppliedResource",
    "Change",
    "Existing",
    "KIND_NAMES",
    "LookupKind",
    "ManagedKind",
    "NotFound",
    "ApplyContext",
    "PlanContext",
    "RESOURCE_KINDS",
    "ResourceKind",
    "Usage",
    "kind_for",
    "managed_kind_for",
]
