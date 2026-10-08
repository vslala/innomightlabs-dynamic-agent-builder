"""What every resource kind provides. Each kind wraps existing services; none of them call HTTP routes."""

from dataclasses import dataclass, field
from typing import ClassVar, Generic, Optional, TypeVar

from fastapi import BackgroundTasks
from pydantic import BaseModel

from src.blueprints.issues import BlueprintIssue


@dataclass
class AppliedResource:
    name: str
    kind: str
    id: str
    #: What `outputs` may reference as {{ resources.<name>.<attribute> }}.
    attributes: dict[str, str] = field(default_factory=dict)
    #: Ids rollback needs beyond `id`, e.g. installed skills. Never shown.
    cleanup: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanContext:
    user_email: str


@dataclass
class ApplyContext:
    user_email: str
    #: Set when applying from an HTTP request; a tool call from a chat turn has none.
    background_tasks: Optional[BackgroundTasks] = None
    #: Resources created so far, by name, so references resolve to real ids.
    applied: dict[str, AppliedResource] = field(default_factory=dict)


@dataclass(frozen=True)
class Usage:
    """What a resource counts against the owner's subscription limits."""

    agents: int = 0
    kb_pages: int = 0


SpecT = TypeVar("SpecT", bound=BaseModel)


class ResourceKind(Generic[SpecT]):
    kind: ClassVar[str]
    spec_model: ClassVar[type[BaseModel]]
    #: Attribute names `apply` fills in, listed in the catalog and checked in `outputs`.
    exposes: ClassVar[tuple[str, ...]]

    def validate(self, name: str, spec: SpecT) -> list[BlueprintIssue]:
        """Checks that need nothing but the spec. Run with every validation."""
        return []

    def check(self, name: str, spec: SpecT, ctx: PlanContext) -> list[BlueprintIssue]:
        """Checks against the owner's account (providers, connections, names). Run by the plan."""
        return []

    def usage(self, spec: SpecT) -> Usage:
        return Usage()

    def describe(self, name: str, spec: SpecT) -> str:
        raise NotImplementedError

    def apply(self, name: str, spec: SpecT, ctx: ApplyContext) -> AppliedResource:
        raise NotImplementedError

    def start(self, applied: AppliedResource, spec: SpecT, ctx: ApplyContext) -> None:
        """Runs once every resource exists, so work that can't be undone (a crawl) starts last."""

    def rollback(self, applied: AppliedResource, ctx: ApplyContext) -> None:
        raise NotImplementedError
