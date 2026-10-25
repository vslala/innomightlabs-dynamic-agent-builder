"""Reads an uploaded document (PDF, Office file or scan) into Markdown, tables and page images with Docling.

Docling's models take about 18 seconds to load, so one converter is built on first use and kept for the life of the
process. Converting is CPU-bound and blocking, so it runs in a thread, one document at a time by default.
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import tempfile
import threading
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.infra_cli_runner.models import DocumentPage, DocumentParseResponse, DocumentTable

if TYPE_CHECKING:
    from docling_core.types.doc import DoclingDocument

IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"})
SUPPORTED_SUFFIXES = frozenset({".pdf", ".docx", ".pptx", ".xlsx", *IMAGE_SUFFIXES})


class UnsupportedDocument(Exception):
    """The file's extension isn't one Docling is set up to read here."""


class DocumentTooLarge(Exception):
    """The file has more bytes or pages than the runner accepts."""


class ConversionFailed(Exception):
    """Docling couldn't read the file; the message says why, briefly."""


class DoclingUnavailable(Exception):
    """Docling isn't installed in this environment."""


#: Reads a document at a path into Docling's document. The real one runs the models; tests pass their own.
Convert = Callable[[Path], "DoclingDocument"]


class DocumentParser:
    def __init__(self, *, convert: Convert | None = None) -> None:
        self._convert = convert or self._convert_with_docling
        self._slots = asyncio.Semaphore(int(os.getenv("DOCUMENT_PARSE_CONCURRENCY", "1")))
        self.max_bytes = int(os.getenv("DOCUMENT_PARSE_MAX_BYTES", str(25 * 1024 * 1024)))
        self.max_pages = int(os.getenv("DOCUMENT_PARSE_MAX_PAGES", "100"))
        self._converter: Any = None
        self._converter_lock = threading.Lock()

    async def parse(self, filename: str, content: bytes) -> DocumentParseResponse:
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise UnsupportedDocument(f"unsupported file type {suffix or '(none)'}: use one of {', '.join(sorted(SUPPORTED_SUFFIXES))}")
        if len(content) > self.max_bytes:
            raise DocumentTooLarge(f"the file is larger than {self.max_bytes} bytes")
        async with self._slots:
            return await asyncio.to_thread(self._parse, suffix, content)

    def _parse(self, suffix: str, content: bytes) -> DocumentParseResponse:
        with tempfile.TemporaryDirectory(prefix="document-parse-") as directory:
            # A fixed name: the caller's filename only decides the format, and never becomes a path.
            path = Path(directory) / f"document{suffix}"
            path.write_bytes(content)
            if suffix == ".pdf":
                self._check_pdf_pages(path)
            doc = self._convert(path)
        if len(doc.pages) > self.max_pages:
            raise DocumentTooLarge(f"the document has more than {self.max_pages} pages")
        return _shape(doc, with_page_images=suffix == ".pdf")

    def _check_pdf_pages(self, path: Path) -> None:
        """Counts a PDF's pages before the models see it: opening one is cheap, converting 500 pages is not."""
        import pypdfium2  # type: ignore[import-untyped]

        try:
            pdf = pypdfium2.PdfDocument(path)
        except pypdfium2.PdfiumError as exc:
            raise ConversionFailed(f"not a readable PDF: {exc}") from exc
        try:
            if len(pdf) > self.max_pages:
                raise DocumentTooLarge(f"the document has more than {self.max_pages} pages")
        finally:
            pdf.close()

    def _convert_with_docling(self, path: Path) -> DoclingDocument:
        converter = self._loaded_converter()
        try:
            return converter.convert(path).document
        except Exception as exc:  # Docling raises many kinds; the caller only needs to know it failed and roughly why.
            reason = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
            raise ConversionFailed(reason[:200]) from exc

    def _loaded_converter(self) -> Any:
        with self._converter_lock:
            if self._converter is None:
                self._converter = _build_converter()
            return self._converter


def _build_converter() -> Any:
    try:
        from docling.datamodel import layout_model_specs
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import LayoutOptions, PdfPipelineOptions
        from docling.document_converter import DocumentConverter, ImageFormatOption, PdfFormatOption
    except ImportError as exc:
        raise DoclingUnavailable(f"docling is not installed: {exc}") from exc

    options = PdfPipelineOptions(
        # The default layout model takes a page with a decorated background (ADP payslips) for one big picture and
        # drops every word on it; heron_101 reads those pages. Found on a trial of 51 real payslips and invoices.
        layout_options=LayoutOptions(model_spec=layout_model_specs.DOCLING_LAYOUT_HERON_101),
        do_ocr=True,
        do_table_structure=True,
        generate_page_images=True,
        images_scale=2.0,
        # The image bakes the models in here; without it Docling downloads them, which a deployed runner must not do.
        artifacts_path=os.getenv("DOCLING_ARTIFACTS_PATH") or None,
    )
    return DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.IMAGE, InputFormat.DOCX, InputFormat.PPTX, InputFormat.XLSX],
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=options),
            InputFormat.IMAGE: ImageFormatOption(pipeline_options=options),
        },
    )


def _shape(doc: DoclingDocument, *, with_page_images: bool) -> DocumentParseResponse:
    from docling_core.types.doc import ImageRefMode

    # Office files have no pages in Docling's model; they read as one.
    page_numbers = sorted(doc.pages) or [1]
    pages = [
        DocumentPage(
            page=page_no,
            markdown=doc.export_to_markdown(page_no=page_no if doc.pages else None, image_mode=ImageRefMode.PLACEHOLDER),
            png_base64=_page_png(doc, page_no) if with_page_images else None,
        )
        for page_no in page_numbers
    ]
    structured = doc.export_to_dict()
    # The page renders are already in `pages`; a second base64 copy of every page would double the response.
    for page in structured.get("pages", {}).values():
        page.pop("image", None)
    return DocumentParseResponse(
        markdown=doc.export_to_markdown(image_mode=ImageRefMode.PLACEHOLDER),
        page_count=len(page_numbers),
        tables=[_table(doc, table) for table in doc.tables],
        structured=structured,
        pages=pages,
    )


def _table(doc: DoclingDocument, table: Any) -> DocumentTable:
    import pandas  # type: ignore[import-untyped]

    frame = table.export_to_dataframe(doc=doc)
    rows = [[str(cell) for cell in row] for row in frame.itertuples(index=False)]
    # A table Docling found no header row in gets numbered columns; those numbers aren't the document's text.
    if not isinstance(frame.columns, pandas.RangeIndex):
        rows.insert(0, [str(name) for name in frame.columns])
    return DocumentTable(page=table.prov[0].page_no if table.prov else 1, rows=rows)


def _page_png(doc: DoclingDocument, page_no: int) -> str | None:
    page = doc.pages.get(page_no)
    image = page.image.pil_image if page and page.image else None
    if image is None:
        return None
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


@lru_cache
def get_document_parser() -> DocumentParser:
    return DocumentParser()
