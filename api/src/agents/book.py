"""A reference book an agent reads like a book: an index always in its prompt, pages opened on demand.

An agent that builds with many resources can't carry every schema in its prompt, and doesn't need to: it
needs to know what exists (the index) and the detail of what it is working with right now (the open pages).
Pages come from page sources, so adding a source, or a page to one, teaches the agent without touching
its prompt. Nothing here knows what the pages are about; the blueprint pages live in `blueprints/book.py`.

Pages nest. A page's id is its place: `account/Agent/a-1/instructions` is under `account/Agent/a-1`. The index lists
only the chapters' own pages; an opened page lists the pages under it, so the agent goes deeper only where the
question leads. Some pages can't be written ahead of time, because they show the reader's own data: a resolver makes
those when they're opened, so a book never reads an account it isn't asked about.

An opened page stays in the prompt for a few turns (`retention`), because chat history keeps messages, not
tool results. Opening it again keeps it longer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Iterable, Iterator, Protocol

SEARCH_LIMIT = 5


@dataclass(frozen=True)
class Page:
    #: Stable and path-like, e.g. "kind/Agent" or "skill/lead_capture". Pages are opened by it, and a page's children
    #: have ids under it ("kind/Automation/steps").
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
    #: The pages under this one. Listed by their index lines when this page is open; each is opened by its id.
    children: tuple["Page", ...] = ()


@dataclass(frozen=True)
class Chapter:
    title: str
    intro: str
    pages: tuple[Page, ...]


class PageSource(Protocol):
    """One chapter's worth of pages, generated from wherever they're defined."""

    def chapter(self) -> Chapter: ...


class PageResolver(Protocol):
    """Pages made when they're opened, for every id under `prefix`: ones that show the reader's own data."""

    prefix: str

    def resolve(self, page_id: str) -> Page | None: ...

    def searchable(self, prefix: str) -> Iterable[Page]:
        """The index lines of its pages under `prefix` that search looks through. Called only when a search reaches
        this resolver, so a narrow prefix reads little."""
        ...


@dataclass(frozen=True)
class Opened:
    pages: list[Page] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


class Book:
    def __init__(self, chapters: Iterable[Chapter], resolvers: Iterable[PageResolver] = ()):
        self.chapters = tuple(chapters)
        self.resolvers = tuple(resolvers)
        #: Every page written ahead of time, nested ones too.
        self._pages = {page.id: page for chapter in self.chapters for page in _with_children(chapter.pages)}
        #: Pages resolved so far: a book is built for one turn, so it reads each one once.
        self._resolved: dict[str, Page | None] = {}

    @classmethod
    def from_sources(cls, sources: Iterable[PageSource], resolvers: Iterable[PageResolver] = ()) -> "Book":
        return cls((source.chapter() for source in sources), resolvers)

    def get(self, page_id: str) -> Page | None:
        """The page, made by its resolver when one covers the id. An index page under a resolver's prefix is only its
        index line: the resolver makes the page itself."""
        resolver = next((resolver for resolver in self.resolvers if page_id.startswith(resolver.prefix)), None)
        if resolver is None:
            return self._pages.get(page_id)
        if page_id not in self._resolved:
            self._resolved[page_id] = resolver.resolve(page_id)
        return self._resolved[page_id]

    @property
    def page_ids(self) -> list[str]:
        """The pages written ahead of time. Resolved ones aren't known until they're opened."""
        return list(self._pages)

    def open(self, page_ids: Iterable[str]) -> Opened:
        opened = Opened()
        for page_id in dict.fromkeys(page_id.strip() for page_id in page_ids):
            page = self.get(page_id)
            if page:
                opened.pages.append(page)
            else:
                opened.unknown.append(page_id)
                opened.suggestions.extend(get_close_matches(page_id, self._pages, n=2, cutoff=0.5))
        return opened

    def search(self, query: str, prefix: str = "", limit: int = SEARCH_LIMIT) -> list[Page]:
        """Keyword search over the pages whose ids start with `prefix`: the ones written ahead of time, and what each
        resolver the prefix reaches offers. Titles and ids count most, then the index lines, then the page text. With
        no query, the pages under `prefix` (not the one it names) in book order."""
        terms = _words(query)
        if not terms and not prefix:
            return []
        candidates = {page.id: page for page in self._pages.values() if page.id.startswith(prefix)}
        for resolver in self.resolvers:
            if resolver.prefix.startswith(prefix) or prefix.startswith(resolver.prefix):
                candidates.update((page.id, page) for page in resolver.searchable(prefix) if page.id.startswith(prefix))
        if not terms:
            return [page for page in candidates.values() if page.id != prefix][:limit]
        scored = [
            (score, position, page)
            for position, page in enumerate(candidates.values())
            if (score := _score(page, terms))
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [page for _, _, page in scored[:limit]]


def _with_children(pages: Iterable[Page]) -> Iterator[Page]:
    for page in pages:
        yield page
        yield from _with_children(page.children)


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
