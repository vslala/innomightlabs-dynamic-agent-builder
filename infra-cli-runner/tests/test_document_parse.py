from __future__ import annotations

import base64
import io
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import pypdfium2
from docling_core.types.doc import BoundingBox, DocItemLabel, DoclingDocument, ImageRef, ProvenanceItem, Size, TableCell, TableData
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from main import app
from src.infra_cli_runner.documents import ConversionFailed, DocumentParser, get_document_parser

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def payslip(path: Path) -> DoclingDocument:
    """What Docling makes of a one-page payslip: a heading, a pay table with a header row, a table with none."""
    doc = DoclingDocument(name=path.stem)
    doc.add_page(page_no=1, size=Size(width=200, height=100), image=ImageRef.from_pil(Image.new("RGB", (200, 100), "white"), dpi=72))
    prov = ProvenanceItem(page_no=1, bbox=BoundingBox(l=0, t=0, r=100, b=50), charspan=(0, 0))
    doc.add_heading("Payslip", prov=prov)
    doc.add_table(data=grid([["Item", "Amount"], ["Net pay", "5,608.87"]], header_rows=1), prov=prov)
    doc.add_table(data=grid([["Employee", "A. Person"]], header_rows=0))
    return doc


def grid(rows: list[list[str]], *, header_rows: int) -> TableData:
    cells = [
        TableCell(
            text=text, start_row_offset_idx=r, end_row_offset_idx=r + 1, start_col_offset_idx=c, end_col_offset_idx=c + 1,
            column_header=r < header_rows,
        )
        for r, row in enumerate(rows)
        for c, text in enumerate(row)
    ]
    return TableData(num_rows=len(rows), num_cols=len(rows[0]), table_cells=cells)


def office_file(path: Path) -> DoclingDocument:
    doc = DoclingDocument(name=path.stem)
    doc.add_text(label=DocItemLabel.TEXT, text="Quarterly report")
    return doc


def blank_pdf(pages: int) -> bytes:
    pdf = pypdfium2.PdfDocument.new()
    for _ in range(pages):
        pdf.new_page(200, 100)
    buffer = io.BytesIO()
    pdf.save(buffer)
    pdf.close()
    return buffer.getvalue()


class DocumentParseEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.env = patch.dict(os.environ, {"CLI_RUNNER_SHARED_TOKEN": "secret", "DOCUMENT_PARSE_MAX_BYTES": "4096", "DOCUMENT_PARSE_MAX_PAGES": "3"})
        self.env.start()
        self.converted: list[Path] = []

        def convert(path: Path) -> DoclingDocument:
            self.converted.append(path)
            if path.suffix == ".docx":
                return office_file(path)
            if path.read_bytes() == b"broken":
                raise ConversionFailed("file format not supported")
            return payslip(path)

        app.dependency_overrides[get_document_parser] = lambda: DocumentParser(convert=convert)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.env.stop()

    def post(self, filename: str, content: bytes, token: str | None = "secret") -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post("/v1/documents/parse", files={"file": (filename, content)}, headers=headers)

    def test_requires_the_bearer_token(self) -> None:
        self.assertEqual(self.post("payslip.pdf", blank_pdf(1), token=None).status_code, 401)
        self.assertEqual(self.post("payslip.pdf", blank_pdf(1), token="wrong").status_code, 401)
        self.assertEqual(self.converted, [])

    def test_an_unsupported_extension_is_a_bad_request(self) -> None:
        for name in ("notes.txt", "page.html", "archive.zip", "no_extension"):
            response = self.post(name, b"hello")
            self.assertEqual(response.status_code, 400, name)
            self.assertIn("unsupported file type", response.json()["detail"])

    def test_a_file_over_the_byte_limit_is_too_large(self) -> None:
        response = self.post("scan.png", b"x" * 4097)
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.converted, [])

    def test_a_pdf_with_too_many_pages_is_refused_before_conversion(self) -> None:
        response = self.post("statement.pdf", blank_pdf(4))
        self.assertEqual(response.status_code, 413)
        self.assertIn("more than 3 pages", response.json()["detail"])
        self.assertEqual(self.converted, [])

    def test_a_file_that_is_not_a_pdf_fails_to_convert(self) -> None:
        response = self.post("payslip.pdf", b"not a pdf at all")
        self.assertEqual(response.status_code, 422)

    def test_a_conversion_failure_is_unprocessable(self) -> None:
        response = self.post("scan.png", b"broken")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "file format not supported")

    def test_returns_markdown_tables_and_pages(self) -> None:
        response = self.post("Payslip.PDF", blank_pdf(1))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("Net pay", body["markdown"])
        self.assertEqual(body["page_count"], 1)
        self.assertEqual(
            body["tables"],
            [
                {"page": 1, "rows": [["Item", "Amount"], ["Net pay", "5,608.87"]]},
                {"page": 1, "rows": [["Employee", "A. Person"]]},
            ],
        )
        self.assertEqual(body["structured"]["name"], "document")
        self.assertNotIn("image", body["structured"]["pages"]["1"])
        [page] = body["pages"]
        self.assertEqual(page["page"], 1)
        self.assertIn("Payslip", page["markdown"])
        self.assertTrue(base64.b64decode(page["png_base64"]).startswith(PNG_SIGNATURE))
        self.assertEqual(self.converted[0].name, "document.pdf")

    def test_only_pdfs_carry_page_renders(self) -> None:
        [page] = self.post("scan.jpg", b"jpeg bytes").json()["pages"]
        self.assertIsNone(page["png_base64"])

    def test_an_office_file_reads_as_one_page(self) -> None:
        body = self.post("report.docx", b"docx bytes").json()
        self.assertEqual(body["page_count"], 1)
        self.assertEqual(body["tables"], [])
        self.assertEqual(body["pages"], [{"page": 1, "markdown": "Quarterly report", "png_base64": None}])

    def test_the_upload_is_removed_after_parsing(self) -> None:
        self.post("payslip.pdf", blank_pdf(1))
        self.assertFalse(self.converted[0].exists())


def docling_models_available() -> bool:
    artifacts = os.getenv("DOCLING_ARTIFACTS_PATH")
    if artifacts:
        return (Path(artifacts) / "docling-project--docling-layout-heron-101").is_dir()
    hub = Path(os.getenv("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    return (hub / "models--docling-project--docling-layout-heron-101").is_dir()


@unittest.skipUnless(os.getenv("DOCLING_SMOKE") == "1", "slow (loads Docling's models): set DOCLING_SMOKE=1 to run")
@unittest.skipUnless(docling_models_available(), "Docling's models are not downloaded (see the README)")
class DoclingSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_a_scanned_payslip(self) -> None:
        image = Image.new("RGB", (1200, 400), "white")
        ImageDraw.Draw(image).text((60, 150), "Net pay 5,608.87", fill="black", font=ImageFont.load_default(size=72))
        buffer = io.BytesIO()
        image.save(buffer, format="PDF")

        parsed = await DocumentParser().parse("payslip.pdf", buffer.getvalue())

        self.assertEqual(parsed.page_count, 1)
        self.assertIn("5,608.87", parsed.markdown)
        self.assertIsNotNone(parsed.pages[0].png_base64)


if __name__ == "__main__":
    unittest.main()
