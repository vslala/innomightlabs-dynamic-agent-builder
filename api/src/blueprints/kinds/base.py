"""What every resource kind provides. Each kind wraps existing services; none of them call HTTP routes.

A blueprint is applied against what already exists: each resource is matched to an existing one (by `id`, else
by name), compared with it, and then created, updated or left alone. Applying the same blueprint twice changes
nothing the second time.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Generic, Literal, Optional, TypeVar

from fastapi import BackgroundTasks
from pydantic import BaseModel

from src.blueprints.issues import BlueprintIssue


class Action(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class Existing:
    """A resource that's already in the owner's account, as the plan found it."""

    id: str
    #: The stored model (Agent, KnowledgeBase, AgentApiKey) at plan time; an update restores it on rollback.
    record: Any
    matched_by: Literal["id", "name"]
    #: Whatever else the kind loaded to compare against (an agent's skills and linked knowledge bases).
    related: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Change:
    action: Action
    existing: Optional[Existing] = None
    #: What an update changes, in plain words ("add skill lead capture").
    changes: tuple[str, ...] = ()


@dataclass
class AppliedResource:
    name: str
    kind: str
    id: str
    #: What `outputs` may reference as {{ resources.<name>.<attribute> }}.
    attributes: dict[str, str] = field(default_factory=dict)
    #: Ids rollback needs beyond `id`, e.g. installed skills. Never shown.
    cleanup: dict[str, list[str]] = field(default_factory=dict)
    #: For an update: what to put back if a later step fails.
    previous: Any = None
    #: Whether `start` has work to do (a knowledge base whose crawl changed).
    needs_start: bool = True


@dataclass
class PlanContext:
    user_email: str
    #: Resources matched so far, by blueprint name, so later ones can resolve references to them.
    matched: dict[str, Existing] = field(default_factory=dict)


@dataclass
class ApplyContext:
    user_email: str
    #: Set when applying from an HTTP request; a tool call from a chat turn has none.
    background_tasks: Optional[BackgroundTasks] = None
    #: Resources created, updated or kept so far, by name, so references resolve to real ids.
    applied: dict[str, AppliedResource] = field(default_factory=dict)


@dataclass(frozen=True)
class Usage:
    """What a resource counts against the owner's subscription limits."""

    agents: int = 0
    kb_pages: int = 0


class NotFound(Exception):
    """A resource names an `id` that isn't in the owner's account."""


SpecT = TypeVar("SpecT", bound=BaseModel)


class ResourceKind(Generic[SpecT]):
    kind: ClassVar[str]
    #: How the kind is named to people, in plans and drawings.
    label: ClassVar[str]
    spec_model: ClassVar[type[BaseModel]]
    #: Attribute names `apply` fills in, listed in the catalog and checked in `outputs`.
    exposes: ClassVar[tuple[str, ...]]

    def validate(self, name: str, spec: SpecT) -> list[BlueprintIssue]:
        """Checks that need nothing but the spec. Run with every validation."""
        return []

    def find_existing(self, name: str, spec: SpecT, ctx: PlanContext) -> Optional[Existing]:
        """The resource this one updates: the one with its `id` (raising NotFound if there's none), else one
        with the same name. None means it will be created."""
        return None

    def differences(self, name: str, spec: SpecT, existing: Existing, ctx: PlanContext) -> list[str]:
        """What updating `existing` to match the spec changes, in plain words. Empty means nothing to do."""
        return []

    def check(self, name: str, spec: SpecT, change: Change, ctx: PlanContext) -> list[BlueprintIssue]:
        """Checks against the owner's account (providers, connections, names). Run by the plan."""
        return []

    def usage(self, spec: SpecT, change: Change) -> Usage:
        return Usage()

    def describe(self, name: str, spec: SpecT) -> str:
        """The plan's sentence for creating this resource."""
        raise NotImplementedError

    def apply(self, name: str, spec: SpecT, ctx: ApplyContext) -> AppliedResource:
        """Create it."""
        raise NotImplementedError

    def update(self, name: str, spec: SpecT, change: Change, ctx: ApplyContext) -> AppliedResource:
        """Change the existing resource to match the spec. Anything that can't be undone waits for `finalize`."""
        raise NotImplementedError

    def kept(self, name: str, change: Change) -> AppliedResource:
        """An unchanged resource, so references to it and outputs about it still resolve."""
        raise NotImplementedError

    def start(self, applied: AppliedResource, spec: SpecT, ctx: ApplyContext) -> None:
        """Runs once every resource exists, so work that can't be undone (a crawl) starts last."""

    def rollback(self, applied: AppliedResource, ctx: ApplyContext) -> None:
        """Undo a create."""
        raise NotImplementedError

    def restore(self, applied: AppliedResource, ctx: ApplyContext) -> None:
        """Undo an update, from `applied.previous`."""
        raise NotImplementedError
