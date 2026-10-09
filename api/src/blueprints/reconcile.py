"""What applying a resource's spec changes, worked out the same way for every kind.

Three trees of the same shape are compared, field by field, with the rule each field declares (`diff.py`):

- **now**: the spec in the blueprint;
- **before**: what was declared last time (a kit's last applied version), or None when nothing remembers it;
- **actual**: the resource as it is, read back as a spec by its kind's `observe`.

Pass one compares before with now: what the person changed. Pass two compares that with actual: what's left is
the work. A field the person didn't change but that differs from actual was changed outside the blueprint; it's
reported as drift and left alone. Without `before`, the actual state stands in for it, so every difference is work.

Items in a collection are matched by key. One the person added is added; one they changed is changed; one they
took away (in before, not now) is taken away, and so is one named in the field's explicit removals list. One that
was never declared is never touched, even when it's there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

from pydantic import BaseModel

from src.blueprints.diff import Each, Scalar


@dataclass(frozen=True)
class SetField:
    field: str
    value: Any
    #: None when another field of its group already says the change.
    says: Optional[str]


@dataclass(frozen=True)
class Drift:
    """Changed outside the blueprint, and left as it is."""

    field: str
    actual: Any


@dataclass(frozen=True)
class ItemChange:
    field: str
    key: str
    #: The item as the spec writes it; None for one taken away.
    now: Any
    #: The item as it is; None for one added.
    actual: Any
    says: str


@dataclass
class Outcome:
    sets: list[SetField] = field(default_factory=list)
    added: list[ItemChange] = field(default_factory=list)
    changed: list[ItemChange] = field(default_factory=list)
    removed: list[ItemChange] = field(default_factory=list)
    drift: list[Drift] = field(default_factory=list)

    def values(self, model: type[BaseModel]) -> dict[str, Any]:
        """The changed fields that are saved, by the stored field each `Scalar` names."""
        records = record_fields(model)
        return {record: change.value for change in self.sets if (record := records.get(change.field))}

    def sets_field(self, name: str) -> bool:
        return any(change.field == name for change in self.sets)

    def says(self) -> tuple[str, ...]:
        """What the field changes say, once per group."""
        return tuple(change.says for change in self.sets if change.says)

    def items(self, kind: str, field_name: str) -> list[ItemChange]:
        return [item for item in getattr(self, kind) if item.field == field_name]


@dataclass(frozen=True)
class Context:
    #: How people know each resource in the blueprint, by name, for the plan's wording.
    titles: Mapping[str, str] = field(default_factory=dict)
    #: Resources being deleted in this blueprint; their own delete disconnects them.
    removing: frozenset[str] = frozenset()
    #: Per collection field, an item's identity. By default an item is its own key.
    keys: Mapping[str, Callable[[Any], str]] = field(default_factory=dict)
    #: Per collection field, whether an item asks for something different from what's there.
    differs: Mapping[str, Callable[[Any, Any], bool]] = field(default_factory=dict)
    #: Per collection field, whether a name in the removals list means this existing item.
    named_by: Mapping[str, Callable[[str, Any], bool]] = field(default_factory=dict)


def rules(model: type[BaseModel]) -> dict[str, Scalar | Each]:
    """Each field's comparison rule, from its type's metadata."""
    found: dict[str, Scalar | Each] = {}
    for name, info in model.model_fields.items():
        rule = next((item for item in info.metadata if isinstance(item, (Scalar, Each))), None)
        if rule is not None:
            found[name] = rule
    return found


def record_fields(model: type[BaseModel]) -> dict[str, Optional[str]]:
    """Spec field → the stored field its `Scalar` is written to."""
    return {name: rule.record for name, rule in rules(model).items() if isinstance(rule, Scalar)}


def reconcile(
    now: BaseModel,
    actual: Optional[Mapping[str, Any]],
    before: Optional[Mapping[str, Any]] = None,
    ctx: Context = Context(),
) -> Outcome:
    outcome = Outcome()
    said: set[str] = set()
    observed = actual or {}
    for name, rule in rules(type(now)).items():
        if isinstance(rule, Scalar):
            _scalar(outcome, said, name, rule, now, observed, before)
        else:
            _each(outcome, name, rule, now, observed, before, ctx)
    return outcome


def _scalar(
    outcome: Outcome,
    said: set[str],
    name: str,
    rule: Scalar,
    now: BaseModel,
    actual: Mapping[str, Any],
    before: Optional[Mapping[str, Any]],
) -> None:
    value = getattr(now, name)
    if rule.omit_none and value is None:
        return
    wanted, there = _normal(rule, value), _normal(rule, actual.get(name))
    declared = _normal(rule, before.get(name)) if before is not None else there
    if declared == wanted:  # the person didn't change it
        if before is not None and there != wanted:
            outcome.drift.append(Drift(name, actual.get(name)))
        return
    if there == wanted:
        return
    group = rule.group or name
    outcome.sets.append(SetField(name, value, None if group in said else rule.phrase(name, value, now)))
    said.add(group)


def _normal(rule: Scalar, value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump()
    if value is not None and rule.normalise:
        value = rule.normalise(value)
    if rule.unordered and value is not None:
        value = sorted(set(value))
    return value


def _each(
    outcome: Outcome,
    name: str,
    rule: Each,
    now: BaseModel,
    actual: Mapping[str, Any],
    before: Optional[Mapping[str, Any]],
    ctx: Context,
) -> None:
    key = ctx.keys.get(name, _identity)
    differs = ctx.differs.get(name)
    wanted = {key(item): item for item in getattr(now, name) or []}
    there = {key(item): item for item in actual.get(name) or []}
    for item_key, item in wanted.items():
        if item_key not in there:
            outcome.added.append(ItemChange(name, item_key, item, None, _phrase(rule.adds, item, ctx)))
        elif rule.changes and differs and differs(item, there[item_key]):
            outcome.changed.append(ItemChange(name, item_key, item, there[item_key], _phrase(rule.changes, item, ctx)))

    taken_away: set[str] = set()
    if before is not None:
        taken_away |= {key(item) for item in before.get(name) or []} - wanted.keys()
    named_by = ctx.named_by.get(name, lambda listed, item: listed == key(item))
    listed_for_removal = (getattr(now, rule.removals_from) or []) if rule.removals_from else []
    for listed in listed_for_removal:
        taken_away |= {item_key for item_key, item in there.items() if named_by(listed, item)}
    for item_key in sorted(taken_away & there.keys(), key=list(there).index):
        item = there[item_key]
        if item_name(item) in ctx.removing:
            continue
        outcome.removed.append(ItemChange(name, item_key, None, item, _phrase(rule.removes, item, ctx)))


def _identity(item: Any) -> str:
    return str(item)


def item_name(item: Any) -> str:
    """How an item is written: a resource name, or a skill entry's id."""
    if isinstance(item, str):
        return item
    if isinstance(item, BaseModel):
        return str(getattr(item, "id", ""))
    return str(item.get("id", "")) if isinstance(item, Mapping) else str(item)


def _phrase(text: str, item: Any, ctx: Context) -> str:
    name = item_name(item)
    return text.format(name=name, label=name.replace("_", " "), title=ctx.titles.get(name, name))
