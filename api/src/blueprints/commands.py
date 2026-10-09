"""What applying a blueprint does, as commands that say how to undo themselves.

Each kind turns a planned resource into small commands: create an agent, link a knowledge base, install a skill.
Each command declares whether it can be undone:

- **Reversible:** it has an exact inverse (unlink what it linked, put back the fields it saved).
- **Compensatable:** a compensating action takes it back (delete the agent it created).
- **Irreversible:** nothing takes it back (delete a knowledge base, start a crawl).

The order isn't written by anyone. `command_order` sorts the commands topologically: a resource is created
before anything uses it, whatever uses a resource goes before the resource is deleted, and every irreversible
command runs after the commit point (`COMMIT`), so a failure before that point can still be undone in full.

Before a command runs, `prepare` reads what its undo needs (the record as it is now, the id it will create), and
the undo is saved on the deployment. So an apply interrupted by a restart can still be put back (see
`executor.recover_interrupted`).
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from enum import Enum
from graphlib import CycleError, TopologicalSorter
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Optional, Union

if TYPE_CHECKING:
    from src.blueprints.kinds.base import AppliedResource, ApplyContext


class Reversibility(str, Enum):
    REVERSIBLE = "reversible"
    COMPENSATABLE = "compensatable"
    IRREVERSIBLE = "irreversible"


@dataclass(frozen=True)
class Undo:
    """How to undo a command: a registered undo action and what it needs. Saved on the deployment as it is."""

    action: str
    args: dict[str, Any]


UndoAction = Callable[[dict[str, Any], str], None]
UNDO_ACTIONS: dict[str, UndoAction] = {}


def undo_action(name: str) -> Callable[[UndoAction], UndoAction]:
    """Registers an undo by name. It must cope with the command not having happened, since an apply interrupted
    part-way can't tell whether its last command ran."""

    def register(action: UndoAction) -> UndoAction:
        UNDO_ACTIONS[name] = action
        return action

    return register


def run_undo(undo: Undo, user_email: str) -> None:
    UNDO_ACTIONS[undo.action](undo.args, user_email)


@dataclass(kw_only=True)
class Command:
    #: The blueprint resource it acts on.
    resource: str
    #: What it changes, in plain words, for the plan ("update its instructions").
    says: tuple[str, ...] = ()
    #: What it takes away, in plain words; listed apart in the plan and recorded on the deployment.
    removal: Optional[str] = None
    #: Other resources that must exist before it runs.
    uses: frozenset[str] = frozenset()

    reversibility: ClassVar[Reversibility] = Reversibility.REVERSIBLE
    #: Makes `resource` available to the commands after it: created, saved or kept. One per resource.
    establishes: ClassVar[bool] = False
    #: Brings `resource` into being, so once it's undone the deployment no longer has it.
    creates: ClassVar[bool] = False
    #: Deletes `resource`, so everything that uses it goes first.
    deletes: ClassVar[bool] = False

    @property
    def name(self) -> str:
        return f"{type(self).__name__} {self.resource}"

    def prepare(self, ctx: "ApplyContext") -> Optional[Undo]:
        """Read what undoing it needs, before it runs. No side effects."""
        return None

    def run(self, ctx: "ApplyContext") -> None:
        raise NotImplementedError


@dataclass(kw_only=True)
class Use(Command):
    """A resource kept as it is, so references to it and outputs about it still resolve."""

    applied: "AppliedResource"

    establishes: ClassVar[bool] = True

    def run(self, ctx: "ApplyContext") -> None:
        ctx.applied[self.resource] = self.applied


class _Commit:
    """The point of no return: everything before it can be undone, nothing after it can."""

    name = "commit"

    def __repr__(self) -> str:
        return "COMMIT"


COMMIT = _Commit()
Step = Union[Command, _Commit]


class OrderError(Exception):
    """The commands can't be ordered: two of them must each come before the other."""


def command_order(commands: list[Command]) -> list[Step]:
    """The commands in the order they must run, with `COMMIT` between the ones that can be undone and the ones that
    can't. Of the commands free to run next, the one given first goes first, so the same blueprint always runs the
    same way."""
    commit = len(commands)
    before: dict[int, set[int]] = {node: set() for node in range(commit + 1)}
    for i, first in enumerate(commands):
        for j, then in enumerate(commands):
            if i == j:
                continue
            # Created (or kept) before anything acts on it or uses it.
            if first.establishes and (then.resource == first.resource or first.resource in then.uses):
                before[j].add(i)
            # Whatever uses a resource, or acts on it, goes before it's deleted.
            if then.deletes and (first.resource == then.resource or then.resource in first.uses):
                before[j].add(i)
    for index, command in enumerate(commands):
        if command.reversibility is Reversibility.IRREVERSIBLE:
            before[index].add(commit)
        else:
            before[commit].add(index)

    sorter = TopologicalSorter(before)
    try:
        sorter.prepare()
    except CycleError as e:
        raise OrderError(" → ".join(_label(commands, node) for node in e.args[1])) from e
    ready: list[int] = []
    order: list[Step] = []
    while sorter.is_active():
        for node in sorter.get_ready():
            heapq.heappush(ready, node)
        node = heapq.heappop(ready)
        order.append(COMMIT if node == commit else commands[node])
        sorter.done(node)
    return order


def _label(commands: list[Command], node: int) -> str:
    return "commit" if node == len(commands) else commands[node].name
