"""What every resource kind provides. Each kind wraps existing services; none of them call HTTP routes.

A blueprint is applied against what already exists: each resource is matched to an existing one (by `id`, else
by name), compared with it, and turned into commands (`commands.py`) that create it, change what differs, or keep
it as it is. Applying the same blueprint twice changes nothing the second time.

Removing is always explicit: leaving something out of a blueprint never removes it. A resource marked `remove`
is deleted, and an update can take parts away (an agent's `remove_knowledge_bases`, `remove_skills`). What can't
be undone runs after everything that can, whatever order the commands come in.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Generic, Literal, Mapping, Optional, TypeVar

from fastapi import BackgroundTasks
from pydantic import BaseModel

from src.blueprints.commands import Command, Use
from src.blueprints.issues import BlueprintIssue
from src.blueprints.references import Reference, field_references


class Action(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    UNCHANGED = "unchanged"
    REMOVE = "remove"


@dataclass(frozen=True)
class Existing:
    """A resource that's already in the owner's account, as the plan found it."""

    id: str
    #: The stored model (Agent, KnowledgeBase, AgentApiKey) at plan time.
    record: Any
    matched_by: Literal["id", "name"]
    #: The resource as it is, written as a spec by its kind's `observe`: what the reconciler compares with.
    observed: dict[str, Any] = field(default_factory=dict)


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


@dataclass
class PlanContext:
    user_email: str
    #: Resources matched so far, by blueprint name, so later ones can resolve references to them.
    matched: dict[str, Existing] = field(default_factory=dict)
    #: Resources planned so far that will be created, by blueprint name. They have no id until apply.
    created: set[str] = field(default_factory=set)
    #: Resources planned so far that will be deleted, by blueprint name.
    removing: set[str] = field(default_factory=set)

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
    #: The resource name it gets when an existing one is written out as a blueprint ("knowledge", "knowledge_2").
    export_name: ClassVar[str]

    def observe(self, record: Any, names: Mapping[str, str]) -> dict[str, Any]:
        """The existing resource as a blueprint writes it, with its `id`: the one place a kind maps what it stores
        back to its spec. `names` gives the blueprint name of each resource it links to, by id; links to
        anything not in `names` are left out."""
        raise NotImplementedError

    def title(self, name: str, spec: SpecT, resources: dict[str, Any]) -> str:
        """How this resource is named to people when the spec may not say."""
        return str(getattr(spec, "name", None) or name)

    def card_details(self, spec: SpecT) -> list[str]:
        """The lines on its card in the blueprint drawing."""
        return []

    def references(self, name: str, spec: SpecT) -> list[Reference]:
        """Where this resource names others: its fields marked `x-ref-kind`."""
        return list(field_references(name, spec))

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

    def commands(self, name: str, spec: SpecT, existing: Optional[Existing], ctx: PlanContext) -> list[Command]:
        """What applying it does: create it when there's nothing `existing`, else change what differs from the spec,
        or keep it as it is. Exactly one command establishes the resource. Each says what it changes or takes away,
        which is what the plan shows."""
        raise NotImplementedError

    def check(self, name: str, spec: SpecT, change: Change, ctx: PlanContext) -> list[BlueprintIssue]:
        """Checks against the owner's account (providers, connections, names). Run by the plan."""
        return []

    def usage(self, spec: SpecT, change: Change) -> Usage:
        return Usage()

    def describe(self, name: str, spec: SpecT) -> str:
        """The plan's sentence for this resource when it isn't there yet."""
        raise NotImplementedError

    def applied(self, name: str, record: Any) -> AppliedResource:
        """The resource as the commands after it see it: its id, and the attributes outputs may show."""
        raise NotImplementedError


class LookupKind(ResourceKind[SpecT]):
    """A kind the account owns and a blueprint only uses, such as an MCP connection holding the person's sign-in.
    It's found and linked to, never created, changed or deleted by a blueprint."""

    def commands(self, name: str, spec: SpecT, existing: Optional[Existing], ctx: PlanContext) -> list[Command]:
        # Not there: `check` says so, and the plan is blocked, so nothing runs.
        return [Use(resource=name, applied=self.applied(name, existing.record))] if existing else []

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

    def delete_commands(self, name: str, spec: SpecT, existing: Existing, removal: str) -> list[Command]:
        """Delete the existing resource a `remove` matched. `removal` is how the plan says it."""
        raise NotImplementedError
