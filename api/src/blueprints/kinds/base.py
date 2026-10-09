"""What every resource kind provides. Each kind wraps existing services; none of them call HTTP routes.

A blueprint is applied against what already exists: each resource is matched to an existing one (by `id`, else
by name), compared with it, and then created, updated or left alone. Applying the same blueprint twice changes
nothing the second time.

Removing is always explicit: leaving something out of a blueprint never removes it. A resource marked `remove`
is deleted, and an update can take parts away (an agent's `remove_knowledge_bases`, `remove_skills`). Removals
run after everything else has been applied, because they can't be undone.
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
    REMOVE = "remove"


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
    #: What it takes away, in plain words ("disconnect knowledge base 'Docs'"). Shown apart, since it can't be undone.
    removals: tuple[str, ...] = ()


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
    #: Resources planned so far that will be created, by blueprint name. They have no id until apply.
    created: set[str] = field(default_factory=set)

    def ids(self) -> dict[str, str]:
        """Blueprint name → id, for everything matched so far."""
        return {name: existing.id for name, existing in self.matched.items()}


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
    """What every kind has: how it's found, checked and shown. Whether a blueprint can create it is up to the
    subclass: `ManagedKind` creates, updates and deletes; `LookupKind` only finds what the account already has."""

    kind: ClassVar[str]
    #: How the kind is named to people, in plans and drawings.
    label: ClassVar[str]
    #: When to use it, in the words a person would ask with. Ada's book index routes on this.
    use_when: ClassVar[str]
    spec_model: ClassVar[type[BaseModel]]
    #: Attribute names `apply` fills in, listed in the catalog and checked in `outputs`.
    exposes: ClassVar[tuple[str, ...]]
    #: How a wire from this kind to a resource naming it reads in the drawing ("knowledge for").
    feeds: ClassVar[str] = ""
    #: Where it is in the dashboard, with `{id}`; empty when it has no page of its own.
    dashboard_path: ClassVar[str] = ""

    def title(self, name: str, spec: SpecT, resources: dict[str, Any]) -> str:
        """How this resource is named to people when the spec may not say."""
        return str(getattr(spec, "name", None) or name)

    def card_details(self, spec: SpecT) -> list[str]:
        """The lines on its card in the blueprint drawing."""
        return []

    def page_sections(self) -> list[str]:
        """Extra Markdown for this kind's page in Ada's book, beyond the fields its spec model gives."""
        return []

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

    def removals(self, name: str, spec: SpecT, existing: Existing, ctx: PlanContext) -> list[str]:
        """What updating `existing` takes away, in plain words. Only what the spec explicitly names."""
        return []

    def check(self, name: str, spec: SpecT, change: Change, ctx: PlanContext) -> list[BlueprintIssue]:
        """Checks against the owner's account (providers, connections, names). Run by the plan."""
        return []

    def usage(self, spec: SpecT, change: Change) -> Usage:
        return Usage()

    def describe(self, name: str, spec: SpecT) -> str:
        """The plan's sentence for this resource when it isn't there yet."""
        raise NotImplementedError

    def kept(self, name: str, change: Change) -> AppliedResource:
        """An unchanged resource, so references to it and outputs about it still resolve."""
        raise NotImplementedError


class LookupKind(ResourceKind[SpecT]):
    """A kind the account owns and a blueprint only uses, such as an MCP connection holding the person's sign-in.
    It's found and linked to, never created, changed or deleted by a blueprint."""

    def validate(self, name: str, spec: SpecT) -> list[BlueprintIssue]:
        if getattr(spec, "remove", False):
            return [BlueprintIssue(
                path=f"resources.{name}.remove",
                message=f"A blueprint can't delete this {self.label}; it belongs to the whole account.",
                hint="Take it off the resources that use it instead.",
            )]
        return []


class ManagedKind(ResourceKind[SpecT]):
    """A kind a blueprint creates, updates and deletes."""

    #: What deleting one takes with it, in plain words, for the plan.
    deletes: ClassVar[str]

    def apply(self, name: str, spec: SpecT, ctx: ApplyContext) -> AppliedResource:
        """Create it."""
        raise NotImplementedError

    def update(self, name: str, spec: SpecT, change: Change, ctx: ApplyContext) -> AppliedResource:
        """Change the existing resource to match the spec. Anything that can't be undone waits for `finalize`."""
        raise NotImplementedError

    def start(self, applied: AppliedResource, spec: SpecT, ctx: ApplyContext) -> None:
        """Runs once every resource exists, so work that can't be undone (a crawl) starts last."""

    def remove_parts(self, applied: AppliedResource, spec: SpecT, change: Change, ctx: ApplyContext) -> None:
        """Take away what `removals` listed. Runs once everything else is applied."""

    def delete(self, change: Change, ctx: ApplyContext) -> None:
        """Delete the existing resource a `remove` matched. Runs once everything else is applied."""
        raise NotImplementedError

    def rollback(self, applied: AppliedResource, ctx: ApplyContext) -> None:
        """Undo a create."""
        raise NotImplementedError

    def restore(self, applied: AppliedResource, ctx: ApplyContext) -> None:
        """Undo an update, from `applied.previous`."""
        raise NotImplementedError
