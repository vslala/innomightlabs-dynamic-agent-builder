"""Finding a tool by the words an agent describes it with, and the one-line summary a tool index shows.

Skills' actions and MCP connectors' tools are searched the same way. Plain scoring is enough: a skill or a connector
has tens of tools with short descriptions, not a corpus.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from typing import TypeVar

SUMMARY_MAX_CHARS = 90

T = TypeVar("T")

#: An item's searchable texts, each with its weight: a word matched in a heavier text counts for more.
WeightedTexts = Callable[[T], Iterable[tuple[str, int]]]


def summarize(description: str) -> str:
    """The description's first sentence, short enough for an index line."""
    text = " ".join(description.split())
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    if len(first) <= SUMMARY_MAX_CHARS:
        return first
    return first[: SUMMARY_MAX_CHARS - 3].rstrip() + "..."


def rank(items: Sequence[T], query: str, limit: int, texts: WeightedTexts[T]) -> list[T]:
    """Up to `limit` items matching the query's words, best first; equal scores keep the items' order."""
    terms = words(query)
    if not terms:
        return []
    scored = [(score, position, item) for position, item in enumerate(items) if (score := _score(texts(item), terms))]
    scored.sort(key=lambda entry: (-entry[0], entry[1]))
    return [item for _, _, item in scored[:limit]]


def words(text: str) -> list[str]:
    return [word for word in re.split(r"[^a-z0-9]+", text.lower()) if word]


def _score(texts: Iterable[tuple[str, int]], terms: list[str]) -> int:
    weighted = [(set(words(text)), weight) for text, weight in texts]
    return sum(weight * _matches(term, text_words) for term in terms for text_words, weight in weighted)


def _matches(term: str, text_words: set[str]) -> int:
    """1 when the term, or a longer or shorter form of it ("keyword"/"keywords"), is present."""
    if term in text_words:
        return 1
    if len(term) < 4:
        return 0
    return int(any(len(word) >= 4 and (word.startswith(term) or term.startswith(word)) for word in text_words))
