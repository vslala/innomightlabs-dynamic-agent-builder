"""What load_skill shows the agent about a skill's actions.

Small skills show every schema. Large (on-demand) skills show an index of names
and summaries, and the agent pulls the schemas it needs by name or by search,
so a 30-action skill does not cost 30 schemas of context on every load.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from src.skills.models import ActionDisclosureMode, SkillActionManifest, SkillManifest

SUMMARY_MAX_CHARS = 90
SEARCH_LIMIT = 5
SUGGESTION_LIMIT = 3


@dataclass(frozen=True)
class DisclosureRequest:
    manifest: SkillManifest
    actions: list[str] | None = None
    query: str | None = None


@dataclass
class DisclosedActions:
    actions: list[SkillActionManifest] = field(default_factory=list)
    index: dict[str, list[tuple[str, str]]] | None = None
    unknown: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


class ActionDisclosure(Protocol):
    def applies(self, request: DisclosureRequest) -> bool: ...

    def disclose(self, request: DisclosureRequest) -> DisclosedActions: ...


class NamedActions:
    """load_skill(skill_id, actions=[...]): exactly the schemas asked for."""

    def applies(self, request: DisclosureRequest) -> bool:
        return bool(request.actions)

    def disclose(self, request: DisclosureRequest) -> DisclosedActions:
        found: list[SkillActionManifest] = []
        unknown: list[str] = []
        for name in request.actions or []:
            action = request.manifest.find_action(name)
            if action is None:
                unknown.append(name)
            elif action not in found:
                found.append(action)
        suggestions = (
            [a.name for a in search_actions(request.manifest, " ".join(unknown), SUGGESTION_LIMIT)]
            if unknown
            else []
        )
        return DisclosedActions(actions=found, unknown=unknown, suggestions=suggestions)


class SearchedActions:
    """load_skill(skill_id, query="..."): the best keyword matches, with schemas."""

    def applies(self, request: DisclosureRequest) -> bool:
        return bool(request.query and request.query.strip())

    def disclose(self, request: DisclosureRequest) -> DisclosedActions:
        return DisclosedActions(actions=search_actions(request.manifest, request.query or "", SEARCH_LIMIT))


class ActionIndex:
    """load_skill(skill_id) on an on-demand skill: names and summaries, no schemas."""

    def applies(self, request: DisclosureRequest) -> bool:
        return request.manifest.action_disclosure is ActionDisclosureMode.ON_DEMAND

    def disclose(self, request: DisclosureRequest) -> DisclosedActions:
        index: dict[str, list[tuple[str, str]]] = {}
        for action in request.manifest.actions:
            index.setdefault(action.group, []).append((action.name, summarize(action.description)))
        return DisclosedActions(index=index)


class AllActions:
    """load_skill(skill_id) on an eager skill: every schema, as always."""

    def applies(self, request: DisclosureRequest) -> bool:
        return True

    def disclose(self, request: DisclosureRequest) -> DisclosedActions:
        return DisclosedActions(actions=list(request.manifest.actions))


DISCLOSURES: list[ActionDisclosure] = [NamedActions(), SearchedActions(), ActionIndex(), AllActions()]


def disclose(request: DisclosureRequest) -> DisclosedActions:
    return next(d for d in DISCLOSURES if d.applies(request)).disclose(request)


def summarize(description: str) -> str:
    """The description's first sentence, short enough for an index line."""
    text = " ".join(description.split())
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    if len(first) <= SUMMARY_MAX_CHARS:
        return first
    return first[: SUMMARY_MAX_CHARS - 3].rstrip() + "..."


def search_actions(manifest: SkillManifest, query: str, limit: int) -> list[SkillActionManifest]:
    """Keyword search over action names, aliases, groups and descriptions.

    Plain scoring is enough: a skill has tens of short action descriptions, not a corpus.
    """
    exact = manifest.find_action(query.strip())
    if exact:
        return [exact]

    terms = _words(query)
    if not terms:
        return []

    scored = [(score, position, action) for position, action in enumerate(manifest.actions) if (score := _score(action, terms))]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [action for _, _, action in scored[:limit]]


def _score(action: SkillActionManifest, terms: list[str]) -> int:
    names = set(_words(" ".join([action.name, *action.aliases])))
    group = set(_words(action.group))
    description = set(_words(action.description))
    return sum(
        3 * _matches(term, names) + 2 * _matches(term, group) + _matches(term, description)
        for term in terms
    )


def _matches(term: str, words: set[str]) -> int:
    """1 when the term, or a longer or shorter form of it ("keyword"/"keywords"), is present."""
    if term in words:
        return 1
    if len(term) < 4:
        return 0
    return int(any(len(word) >= 4 and (word.startswith(term) or term.startswith(word)) for word in words))


def _words(text: str) -> list[str]:
    return [word for word in re.split(r"[^a-z0-9]+", text.lower()) if word]
