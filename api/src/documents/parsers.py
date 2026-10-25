"""One parser per way of reading a file. `read_document` asks each parser that supports a file and picks a result.

A parser raises `DocumentReadError` when it can't read a file it supports (a damaged PDF, the parsing service down):
that is one parser failing, not the whole read.
"""

import asyncio
import base64
import os
import re
from io import BytesIO
from typing import Optional, Protocol

import httpx

from src.config.settings import settings
from src.documents.models import DocumentReadError, ParsedDocument, ParsedPage, ParsedTable
from src.documents.outline import outline_from_markdown
from src.messages.models import ALLOWED_EXTENSIONS
from src.web_pages.content import fragment_to_markdown

HTML_EXTENSIONS = {".html", ".htm"}
TEXT_EXTENSIONS = ALLOWED_EXTENSIONS - HTML_EXTENSIONS
DOCLING_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
#: The files a web page links to that are documents, by the type the site serves them as.
DOCUMENT_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}


TABLE_SEPARATOR_CELL = re.compile(r"^:?-+:?$")


def compact_tables(markdown: str) -> str:
    """Markdown tables without the padding that aligns their columns: `| Net pay    |   5,608.87 |` is `| Net pay | 5,608.87 |`.

    Docling pads every cell to its column's width, which can make a spreadsheet's Markdown three times its text: three
    times the chunks to embed and the characters an agent reads, for nothing a reader or a model needs.
    """
    lines = []
    for line in markdown.split("\n"):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1:
            cells = [cell.strip() for cell in stripped[1:-1].split("|")]
            if all(TABLE_SEPARATOR_CELL.match(cell) for cell in cells):
                cells = ["---"] * len(cells)
            line = "| " + " | ".join(cells) + " |"
        lines.append(line)
    return "\n".join(lines)


class DocumentParser(Protocol):
    name: str

    def supports(self, filename: str) -> bool: ...

    async def parse(self, data: bytes, filename: str) -> ParsedDocument: ...


def extension(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


class TextParser:
    """Source code, Markdown, CSV and other plain text: the file is the Markdown."""

    name = "text"

    def supports(self, filename: str) -> bool:
        return extension(filename) in TEXT_EXTENSIONS

    async def parse(self, data: bytes, filename: str) -> ParsedDocument:
        markdown = data.decode("utf-8", errors="replace")
        return ParsedDocument(markdown=markdown, parser=self.name, outline=outline_from_markdown(markdown))


class HtmlParser:
    """An HTML file is read like the content of a page (the crawler's reader), minus the chrome-stripping."""

    name = "html"

    def supports(self, filename: str) -> bool:
        return extension(filename) in HTML_EXTENSIONS

    async def parse(self, data: bytes, filename: str) -> ParsedDocument:
        markdown = fragment_to_markdown(data.decode("utf-8", errors="replace"))
        return ParsedDocument(markdown=markdown, parser=self.name, outline=outline_from_markdown(markdown))


class PdfTextLayerParser:
    """The text a PDF carries itself. Plain and fast, with no layout or tables, but it never loses text to a
    layout model's mistakes: it is what `read_document` falls back on when Docling reads far less than is there."""

    name = "pdf_text_layer"

    def supports(self, filename: str) -> bool:
        return extension(filename) == ".pdf"

    async def parse(self, data: bytes, filename: str) -> ParsedDocument:
        return await asyncio.to_thread(self._read, data)

    def _read(self, data: bytes) -> ParsedDocument:
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError

        try:
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted:
                raise DocumentReadError("the PDF is password protected")
            pages = [(page.extract_text() or "").strip() for page in reader.pages]
        except PyPdfError as exc:
            raise DocumentReadError(f"the PDF couldn't be read: {exc}") from exc
        return ParsedDocument(
            markdown="\n\n".join(pages),
            parser=self.name,
            page_count=len(pages),
            pages=[ParsedPage(number=n, markdown=text) for n, text in enumerate(pages, start=1)],
        )


class DoclingParser:
    """PDF, Office files and images, read with Docling (layout, tables, OCR) in the CLI runner, the private sidecar that
    also renders pages for the crawler.

    The runner answers `POST /v1/documents/parse` (multipart `file`) with `{"markdown", "page_count",
    "tables": [{"page", "rows"}], "pages": [{"page", "markdown", "png_base64"}], "structured"}`.
    """

    name = "docling"

    def __init__(self, base_url: str, token: str, timeout_seconds: int, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def supports(self, filename: str) -> bool:
        return extension(filename) in DOCLING_EXTENSIONS

    async def parse(self, data: bytes, filename: str) -> ParsedDocument:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = await client.post(
                    f"{self.base_url}/v1/documents/parse",
                    files={"file": (filename, data)},
                    headers={"Authorization": f"Bearer {self.token}"},
                )
        except httpx.HTTPError as exc:
            raise DocumentReadError(f"the parsing service is unreachable: {exc.__class__.__name__}") from exc
        if response.status_code >= 400:
            raise DocumentReadError(f"the parsing service answered HTTP {response.status_code}: {response.text[:200]}")
        try:
            body = response.json()
            markdown = compact_tables(body["markdown"])
            pages = [
                ParsedPage(
                    number=int(p["page"]),
                    markdown=compact_tables(p.get("markdown") or ""),
                    image=base64.b64decode(p["png_base64"]) if p.get("png_base64") else None,
                )
                for p in body.get("pages", [])
            ]
            return ParsedDocument(
                markdown=markdown,
                parser=self.name,
                page_count=int(body["page_count"]),
                tables=[ParsedTable(page=int(t["page"]), rows=t["rows"]) for t in body.get("tables", [])],
                pages=pages,
                structured=body.get("structured"),
                outline=outline_from_markdown(markdown, pages),
            )
        except (ValueError, KeyError, TypeError) as exc:  # binascii.Error is a ValueError
            raise DocumentReadError("the parsing service returned an invalid response") from exc


def accepted_extensions() -> set[str]:
    """What an upload form offers: every kind the configured parsers read."""
    accepted = TEXT_EXTENSIONS | HTML_EXTENSIONS | {".pdf"}
    if settings.cli_runner_base_url and settings.cli_runner_shared_token:
        accepted |= DOCLING_EXTENSIONS
    return accepted


def default_parsers() -> list[DocumentParser]:
    """In order of preference: the richest reading first. Docling is left out where there is no CLI runner to ask."""
    parsers: list[DocumentParser] = [TextParser(), HtmlParser()]
    if settings.cli_runner_base_url and settings.cli_runner_shared_token:
        parsers.append(
            DoclingParser(settings.cli_runner_base_url, settings.cli_runner_shared_token, settings.document_parser_timeout_seconds)
        )
    parsers.append(PdfTextLayerParser())
    return parsers
