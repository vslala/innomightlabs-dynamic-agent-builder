"""A blueprint document as it's written, valid or not.

Ada's draft is often invalid while she works on it, so the code that reads it before validation (which skill
settings the person still has to give, which accounts to connect, which book page explains an issue) can't use the
validated model. `Draft` is the one place that knows the document's raw shape; everything else asks it.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterator, Optional

import yaml  # type: ignore[import-untyped,unused-ignore]


@dataclass(frozen=True)
class SkillEntryRef:
    #: The agent resource it's on.
    resource: str
    agent: dict[str, Any]
    #: Its position in the agent's `skills`, for issue paths.
    index: int
    entry: dict[str, Any]
    #: "<agent>/<skill id>/<n>": the n-th entry of that skill on that agent. Survives the draft being rewritten,
    #: which entry indexes don't.
    key: str


class Draft:
    def __init__(self, text: Optional[str]):
        self.text = text or ""
        try:
            data = yaml.safe_load(self.text)
        except yaml.YAMLError:
            data = None
        self.parsed = isinstance(data, dict)
        self.data: dict[str, Any] = data if isinstance(data, dict) else {}

    @property
    def resources(self) -> dict[str, dict[str, Any]]:
        raw = self.data.get("resources")
        return {name: spec for name, spec in raw.items() if isinstance(spec, dict)} if isinstance(raw, dict) else {}

    def kept(self, kind: str) -> list[tuple[str, dict[str, Any]]]:
        """Resources of a kind that the draft keeps or builds, not ones it removes."""
        return [(name, spec) for name, spec in self.resources.items() if spec.get("kind") == kind and not spec.get("remove")]

    def skill_entries(self) -> Iterator[SkillEntryRef]:
        """Every skill entry on every agent the draft keeps or builds."""
        for name, agent in self.kept("Agent"):
            entries = agent.get("skills")
            seen: dict[str, int] = {}
            for index, entry in enumerate(entries if isinstance(entries, list) else []):
                if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                    continue
                occurrence = seen.get(entry["id"], 0)
                seen[entry["id"]] = occurrence + 1
                yield SkillEntryRef(name, agent, index, entry, f"{name}/{entry['id']}/{occurrence}")

    def with_skill_settings(self, answers: dict[str, dict[str, Any]]) -> "Draft":
        """The draft with the person's answers in each skill's `config`. Settings the draft already has are kept."""
        draft, changed = self._copy(), False
        for ref in draft.skill_entries():
            given = answers.get(ref.key)
            if not given:
                continue
            config = ref.entry.setdefault("config", {}) if isinstance(ref.entry.get("config", {}), dict) else None
            for field_name, value in given.items():
                if config is not None and config.get(field_name) in (None, ""):
                    config[field_name] = value
                    changed = True
        return Draft(draft.dump()) if changed else self

    def pinned(self, ids: dict[str, str]) -> "Draft":
        """Each named resource pinned to the id it was built as, so the next apply updates it."""
        draft = self._copy()
        for name, resource_id in ids.items():
            resource = draft.resources.get(name)
            if resource is not None:
                # Put `id` right after `kind`, where a reader expects it.
                pinned = {"kind": resource.get("kind"), "id": resource_id}
                pinned.update({key: value for key, value in resource.items() if key not in ("kind", "id")})
                draft.data["resources"][name] = pinned
        return Draft(draft.dump())

    def _copy(self) -> "Draft":
        copy = Draft(None)
        copy.data, copy.parsed = deepcopy(self.data), self.parsed
        return copy

    def dump(self) -> str:
        return yaml.dump(self.data, Dumper=_LiteralDumper, sort_keys=False, allow_unicode=True, width=120)


class _LiteralDumper(yaml.SafeDumper):
    """Multi-line text as a `|` block, as people write instructions."""


def _represent_text(dumper: yaml.SafeDumper, value: str) -> yaml.Node:
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|" if "\n" in value else None)


_LiteralDumper.add_representer(str, _represent_text)
