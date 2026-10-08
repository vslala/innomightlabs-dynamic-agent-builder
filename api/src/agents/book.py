"""A reference book an agent reads like a book: an index always in its prompt, pages opened on demand.

An agent that builds with many resources can't carry every schema in its prompt, and doesn't need to: it
needs to know what exists (the index) and the detail of what it is working with right now (the open pages).
Pages come from page sources, so adding a source, or a page to one, teaches the agent without touching
its prompt. Nothing here knows what the pages are about; the blueprint pages live in `blueprints/book.py`.

An opened page stays in the prompt for a few turns (`retention`), because chat history keeps messages, not
tool results. Opening it again keeps it longer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Iterable, Protocol

SEARCH_LIMIT = 5


@dataclass(frozen=True)
class Page:
    #: Stable and path-like, e.g. "kind/Agent" or "skill/lead_capture". Pages are opened by it.
    id: str
    title: str
    #: One line for the index: what it is.
    summary: str
    #: The page itself, as Markdown.
    body: str
    #: In the person's words, so the index routes on what they ask for ("capture leads").
    use_when: str = ""
    #: Something the reader must know before using it, shown in the index too ("needs a Google account").
    note: str = ""
    related: tuple[str, ...] = ()


@dataclass(frozen=True)
class Chapter:
    title: str
    intro: str
    pages: tuple[Page, ...]


class PageSource(Protocol):
    """One chapter's worth of pages, generated from wherever they're defined."""

    def chapter(self) -> Chapter: ...


@dataclass(frozen=True)
class Opened:
    pages: list[Page] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


class Book:
    def __init__(self, chapters: Iterable[Chapter]):
        self.chapters = tuple(chapters)
        self._pages = {page.id: page for chapter in self.chapters for page in chapter.pages}

    @classmethod
    def from_sources(cls, sources: Iterable[PageSource]) -> "Book":
        return cls(source.chapter() for source in sources)

    def get(self, page_id: str) -> Page | None:
        return self._pages.get(page_id)

    @property
    def page_ids(self) -> list[str]:
        return list(self._pages)

    def open(self, page_ids: Iterable[str]) -> Opened:
        opened = Opened()
        for page_id in dict.fromkeys(page_id.strip() for page_id in page_ids):
            page = self._pages.get(page_id)
            if page:
                opened.pages.append(page)
            else:
                opened.unknown.append(page_id)
                opened.suggestions.extend(get_close_matches(page_id, self._pages, n=2, cutoff=0.5))
        return opened

    def search(self, query: str, limit: int = SEARCH_LIMIT) -> list[Page]:
        """Keyword search. Titles and ids count most, then the index lines, then the page text."""
        terms = _words(query)
        if not terms:
            return []
        scored = [
            (score, position, page)
            for position, page in enumerate(self._pages.values())
            if (score := _score(page, terms))
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [page for _, _, page in scored[:limit]]


def _score(page: Page, terms: list[str]) -> int:
    heading = set(_words(f"{page.id} {page.title}"))
    index_line = set(_words(f"{page.summary} {page.use_when}"))
    body = set(_words(page.body))
    return sum(3 * _matches(term, heading) + 2 * _matches(term, index_line) + _matches(term, body) for term in terms)


def _matches(term: str, words: set[str]) -> int:
    """1 when the term, or a longer or shorter form of it ("lead"/"leads"), is present."""
    if term in words:
        return 1
    if len(term) < 4:
        return 0
    return int(any(len(word) >= 4 and (word.startswith(term) or term.startswith(word)) for word in words))


def _words(text: str) -> list[str]:
    return [word for word in re.split(r"[^a-z0-9]+", text.lower()) if word]


# --- Which pages are open ---------------------------------------------------------------------------------


def open_pages(opened: dict[str, int], page_ids: Iterable[str], turn: int) -> dict[str, int]:
    """`opened` maps a page id to the turn it was last opened in. Opening again restarts its retention."""
    return {**opened, **{page_id: turn for page_id in page_ids}}


def pages_in_view(opened: dict[str, int], turn: int, retention: int) -> list[str]:
    """Pages opened within the last `retention` turns, this one included; most recently opened last."""
    keep = max(1, retention)
    return [page_id for page_id, at in sorted(opened.items(), key=lambda item: item[1]) if turn - at < keep]


def turns_left(opened_at: int, turn: int, retention: int) -> int:
    """Turns a page stays open after this one."""
    return max(1, retention) - 1 - (turn - opened_at)
