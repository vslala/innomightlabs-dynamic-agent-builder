"""`read_document`: the one way to read a file."""

import logging
from typing import Optional

from src.documents.models import DocumentReadError, ParsedDocument, UnsupportedDocument
from src.documents.parsers import DocumentParser, default_parsers

log = logging.getLogger(__name__)

#: Bumped when parsers change what they read: documents read by an older version are read again. 2: Docling tables compacted. 3: an outline is kept.
PARSER_VERSION = 3

#: A later parser's reading replaces the first when it holds more than this many times the text. Layout models can
#: mistake a decorated page for one big picture and drop its text (Amazon payslips): the PDF's own text layer shows it.
MORE_TEXT_FACTOR = 2


async def read_document(
    data: bytes, filename: str, *, parsers: Optional[list[DocumentParser]] = None
) -> ParsedDocument:
    """Read a file with every parser that supports it, and return the best reading.

    The first parser's reading wins, unless a later parser found more than `MORE_TEXT_FACTOR` times its text.
    A parser that fails is skipped; the read fails only when every parser did.
    """
    candidates = parsers_for(filename, parsers)
    if not candidates:
        raise UnsupportedDocument(f"'{filename}' is not a kind of file that can be read")

    readings: list[ParsedDocument] = []
    failures: list[str] = []
    for parser in candidates:
        try:
            readings.append(await parser.parse(data, filename))
        except DocumentReadError as exc:
            log.warning("%s couldn't read %s: %s", parser.name, filename, exc)
            failures.append(f"{parser.name}: {exc}")
    if not readings:
        raise DocumentReadError("; ".join(failures))
    return _best(readings)


def parsers_for(filename: str, parsers: Optional[list[DocumentParser]] = None) -> list[DocumentParser]:
    """The parsers that would read this file, richest first: none means it can't be read."""
    return [p for p in (parsers if parsers is not None else default_parsers()) if p.supports(filename)]


def _best(readings: list[ParsedDocument]) -> ParsedDocument:
    first = readings[0]
    fullest = max(readings, key=lambda r: r.text_chars)
    return fullest if fullest.text_chars > MORE_TEXT_FACTOR * first.text_chars else first
