"""What load_skill shows the agent about a skill's actions.

Small skills show every schema. Large (on-demand) skills show an index of names
and summaries, and the agent pulls the schemas it needs by name or by search,
so a 30-action skill does not cost 30 schemas of context on every load.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from src.common.keyword_search import rank, summarize
from src.skills.models import ActionDisclosureMode, SkillActionManifest, SkillManifest

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


def search_actions(manifest: SkillManifest, query: str, limit: int) -> list[SkillActionManifest]:
    """The exact action the query names, or the best keyword matches over names, aliases, groups and descriptions."""
    exact = manifest.find_action(query.strip())
    if exact:
        return [exact]
    return rank(manifest.actions, query, limit, _searchable_texts)


def _searchable_texts(action: SkillActionManifest) -> list[tuple[str, int]]:
    return [(" ".join([action.name, *action.aliases]), 3), (action.group, 2), (action.description, 1)]
