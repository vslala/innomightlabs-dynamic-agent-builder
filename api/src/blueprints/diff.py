"""How each spec field is compared with what exists, declared next to the field.

A field's rule rides in its type's metadata (`Annotated[str, Scalar(...)]`), so pydantic validates the field as
usual and the published schema doesn't change. The reconciler (`reconcile.py`) reads the rules; nothing compares a
field by hand.

- `Scalar`: equal or not, and written whole.
- `Each`: a collection whose items are matched by a key and added, changed or taken away one at a time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

from pydantic import BaseModel

#: How a change reads in the plan: a format string with `{value}` (and the spec's fields), or a function of the
#: new value and the whole spec.
Says = Union[str, Callable[[Any, Any], str]]


@dataclass(frozen=True)
class Scalar:
    #: How the change reads in the plan.
    says: Says = "change its {field}"
    #: The stored field it's written to. None: the kind writes it its own way (a crawl is started, not saved).
    record: Optional[str] = None
    #: A missing value (None) leaves what's there alone, rather than clearing it.
    omit_none: bool = False
    #: Applied to both sides before comparing (trim text, reduce addresses to origins).
    normalise: Optional[Callable[[Any], Any]] = None
    #: Order doesn't matter: compared as a set.
    unordered: bool = False
    #: Fields that change together and read as one change ("switch to OpenAI · gpt-5"), said once.
    group: Optional[str] = None

    def phrase(self, field: str, value: Any, spec: Any) -> str:
        if callable(self.says):
            return self.says(value, spec)
        return self.says.format(field=field.replace("_", " "), value=value, **_fields(spec))


@dataclass(frozen=True)
class Each:
    """Items matched by key. The kind can give the key (an install's identity); by default an item is its own key.
    Each phrase is a format string with `{name}` (the item as written) and `{title}` (how people know it)."""

    adds: str
    removes: str
    changes: Optional[str] = None
    #: The field that names items to take away. Until a kit remembers what it declared, leaving an item out never
    #: takes it away; only this list does.
    removals_from: Optional[str] = None


def _fields(spec: Any) -> dict[str, Any]:
    return dict(spec) if isinstance(spec, BaseModel) else {}
