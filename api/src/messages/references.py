"""Message references: what a message points at (a document), one strategy per kind.

A kind says how its references are attached when a message is sent, how they read in the conversation the agent sees,
and how `recall_conversation` lists them. `messages` imports no feature: a feature registers its kind when its module
is imported (`conversations/documents.py`). Tool families turn on when the conversation holds a reference of their
kind (`agents/tool_runtime/families.py`). See docs/LLD-message-references-and-tool-families.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Protocol

from pydantic import BaseModel, StringConstraints

from src.exceptions import Refusal
from src.messages.models import Message, MessageReference

if TYPE_CHECKING:
    from src.conversations.models import Conversation

Id = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ReferenceRequest(BaseModel):
    """A reference as a client sends it: the kind and the id; the kind fills in the rest."""

    kind: Id
    id: Id


class ReferenceRefused(Refusal):
    """A reference that can't be attached: an unknown kind, or an id that isn't this conversation's to attach."""


class ReferenceKind(Protocol):
    kind: str

    def attach(self, conversation: "Conversation", ids: list[str]) -> list[MessageReference]:
        """When the message is sent: check each id is this conversation's and not attached yet, mark it attached, and
        return the references. Raises `ReferenceRefused` for one that isn't, attaching none."""
        ...

    def describe(self, conversation: "Conversation", references: list[MessageReference]) -> dict[str, str]:
        """Once per turn, for every reference of this kind the conversation holds: id -> the tag the context shows.
        One lookup for all of them."""
        ...

    def recall_line(self, reference: MessageReference) -> str:
        """The line `recall_conversation` prints, from the reference alone."""
        ...


REFERENCE_KINDS: dict[str, ReferenceKind] = {}


def register(kind: ReferenceKind) -> None:
    REFERENCE_KINDS[kind.kind] = kind


def attach_references(conversation: "Conversation", requests: list[ReferenceRequest]) -> list[MessageReference]:
    """The references a message is sent with, attached by their kinds. Unknown kinds are refused before any is
    attached; ids repeated in the request count once."""
    by_kind: dict[str, list[str]] = {}
    for request in requests:
        if request.kind not in REFERENCE_KINDS:
            raise ReferenceRefused("reference_kind_unknown", f"Can't attach a '{request.kind}'.")
        ids = by_kind.setdefault(request.kind, [])
        if request.id not in ids:
            ids.append(request.id)
    return [reference for kind, ids in by_kind.items() for reference in REFERENCE_KINDS[kind].attach(conversation, ids)]


def references_by_kind(messages: list[Message]) -> dict[str, list[MessageReference]]:
    """Every reference the conversation's messages hold, by kind, each id once."""
    found: dict[str, dict[str, MessageReference]] = {}
    for message in messages:
        for reference in message.references:
            found.setdefault(reference.kind, {}).setdefault(reference.id, reference)
    return {kind: list(references.values()) for kind, references in found.items()}


def reference_tags(
    conversation: "Conversation", references: dict[str, list[MessageReference]]
) -> dict[tuple[str, str], str]:
    """The tag each reference reads as in the context, by (kind, id), from one lookup per kind."""
    tags: dict[tuple[str, str], str] = {}
    for kind, of_kind in references.items():
        strategy = REFERENCE_KINDS.get(kind)
        described = strategy.describe(conversation, of_kind) if strategy else {}
        for reference in of_kind:
            tags[(kind, reference.id)] = described.get(reference.id) or unavailable_tag(reference)
    return tags


def unavailable_tag(reference: MessageReference) -> str:
    """What a reference reads as when its target is gone (deleted), or its kind is no longer registered."""
    return f'<attached kind="{reference.kind}" id="{reference.id}" label="{reference.label}">(no longer available)</attached>'


def recall_line(reference: MessageReference) -> str:
    strategy = REFERENCE_KINDS.get(reference.kind)
    return strategy.recall_line(reference) if strategy else f"[{reference.kind} {reference.id} {reference.label}]"
