"""What a reading says about its own shape: the headings, the pages that hold little text, the tables.

Parsers fill `ParsedDocument.outline` (`outline_from_markdown` serves every parser whose Markdown carries `#` headings);
storage keeps `describe_reading`'s result beside the reading, and `DocumentService.describe` serves it.
"""

import re
from typing import Any, Optional

from src.documents.models import IMAGE_LINK, OutlineEntry, ParsedDocument, ParsedPage

HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t#]*$")
FENCE = re.compile(r"^\s*(```|~~~)")
#: A page with fewer letters and digits than this is probably a scan the reader couldn't read, a chart or a signature.
WEAK_PAGE_CHARS = 50


def outline_from_markdown(markdown: str, pages: Optional[list[ParsedPage]] = None) -> list[OutlineEntry]:
    """The `#` headings (not those inside code fences), with the page each is on when the pages are known."""
    entries: list[OutlineEntry] = []
    in_fence = False
    offset = 0
    page_index = 0
    for line in markdown.splitlines(keepends=True):
        text = line.rstrip("\r\n")
        if FENCE.match(text):
            in_fence = not in_fence
        elif not in_fence:
            match = HEADING.match(text)
            if match:
                page = None
                if pages:
                    # Headings come in page order, so the search for each one carries on from the page of the last
                    found = next((i for i in range(page_index, len(pages)) if text in pages[i].markdown), None)
                    if found is not None:
                        page_index = found
                        page = pages[found].number
                entries.append(OutlineEntry(title=match.group(2).strip(), level=len(match.group(1)), offset=offset, page=page))
        offset += len(line)
    return entries


def weak_pages(pages: list[ParsedPage]) -> list[int]:
    return [p.number for p in pages if sum(c.isalnum() for c in IMAGE_LINK.sub("", p.markdown)) < WEAK_PAGE_CHARS]


def describe_reading(reading: ParsedDocument) -> dict[str, Any]:
    """The JSON stored as `outline.json`."""
    return {
        "headings": [
            {"title": e.title, "level": e.level, "offset": e.offset, "page": e.page} for e in reading.outline
        ],
        "weak_pages": weak_pages(reading.pages),
        "tables": [
            {"number": n, "page": t.page, "rows": max(len(t.rows) - 1, 0), "columns": t.rows[0] if t.rows else []}
            for n, t in enumerate(reading.tables, start=1)
        ],
    }
