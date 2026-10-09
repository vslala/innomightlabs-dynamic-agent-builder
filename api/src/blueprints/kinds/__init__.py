"""Every resource kind a blueprint can create. Adding a capability means adding a spec model to
`spec.Resource` and a kind here."""

from src.blueprints.kinds.agent import AgentKind
from src.blueprints.kinds.base import (
    Action,
    AppliedResource,
    ApplyContext,
    Change,
    Existing,
    NotFound,
    PlanContext,
    ResourceKind,
    Usage,
)
from src.blueprints.kinds.knowledge_base import KnowledgeBaseKind
from src.blueprints.kinds.mcp_connection import McpConnectionKind
from src.blueprints.kinds.widget_key import WidgetKeyKind

RESOURCE_KINDS: tuple[ResourceKind, ...] = (KnowledgeBaseKind(), McpConnectionKind(), AgentKind(), WidgetKeyKind())


def kind_for(name: str) -> ResourceKind:
    return next(kind for kind in RESOURCE_KINDS if kind.kind == name)


__all__ = [
    "Action",
    "AppliedResource",
    "Change",
    "Existing",
    "NotFound",
    "ApplyContext",
    "PlanContext",
    "RESOURCE_KINDS",
    "ResourceKind",
    "Usage",
    "kind_for",
]
