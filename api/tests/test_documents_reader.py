"""Reading a file: the parsers, and which reading `read_document` returns."""

import base64

import httpx
import pytest

from src.documents import DocumentReadError, ParsedDocument, UnsupportedDocument, read_document
from src.documents.parsers import DoclingParser, HtmlParser, PdfTextLayerParser, TextParser, default_parsers
from tests.documents_support import pdf_with_text


class FakeParser:
    def __init__(self, name: str, markdown: str = "", error: str = "", handles: str = ".pdf"):
        self.name, self.markdown, self.error, self.handles = name, markdown, error, handles

    def supports(self, filename: str) -> bool:
        return filename.endswith(self.handles)

    async def parse(self, data: bytes, filename: str) -> ParsedDocument:
        if self.error:
            raise DocumentReadError(self.error)
        return ParsedDocument(markdown=self.markdown, parser=self.name)


async def test_the_first_reading_wins_when_nothing_found_much_more():
    docling = FakeParser("docling", "Net pay 5,608.87 Gross pay 9,391.67")
    layer = FakeParser("layer", "Net pay 5,608.87 Gross pay 9,391.67 Tax")

    assert (await read_document(b"", "a.pdf", parsers=[docling, layer])).parser == "docling"


async def test_a_reading_with_far_more_text_replaces_the_first():
    """The default layout model reads a payslip with a decorated background as one picture and loses its text."""
    docling = FakeParser("docling", "![Image](images/page.png)")
    layer = FakeParser("layer", "Net pay 5,608.87 Gross pay 9,391.67 Tax code 0T")

    assert (await read_document(b"", "a.pdf", parsers=[docling, layer])).parser == "layer"


async def test_a_parser_that_fails_is_skipped():
    docling = FakeParser("docling", error="the parsing service is unreachable")
    layer = FakeParser("layer", "Some text")

    assert (await read_document(b"", "a.pdf", parsers=[docling, layer])).parser == "layer"


async def test_every_parser_failing_fails_the_read_and_says_why():
    parsers = [FakeParser("docling", error="service down"), FakeParser("layer", error="encrypted")]

    with pytest.raises(DocumentReadError, match="docling: service down; layer: encrypted"):
        await read_document(b"", "a.pdf", parsers=parsers)


async def test_a_file_no_parser_supports_is_refused():
    with pytest.raises(UnsupportedDocument):
        await read_document(b"MZ", "setup.exe", parsers=[FakeParser("layer")])


def test_text_chars_ignores_image_links_and_table_padding():
    document = ParsedDocument(markdown="![Image](images/a1b2.png)\n\n| Net | 5,608.87 |\n|-----|---|", parser="x")

    assert document.text_chars == len("Net") + len("560887")


async def test_text_files_are_their_own_markdown():
    parsed = await TextParser().parse("# Title\nbody".encode(), "notes.md")

    assert parsed.markdown == "# Title\nbody"


async def test_html_files_become_markdown_without_scripts():
    parsed = await HtmlParser().parse(b"<h1>Terms</h1><script>track()</script><p>Pay monthly.</p>", "terms.html")

    assert "Terms" in parsed.markdown and "Pay monthly." in parsed.markdown and "track" not in parsed.markdown


async def test_a_pdfs_text_layer_is_read():
    parsed = await PdfTextLayerParser().parse(pdf_with_text("Net pay 5608.87"), "payslip.pdf")

    assert "Net pay 5608.87" in parsed.markdown and parsed.page_count == 1 and parsed.pages[0].number == 1


async def test_a_damaged_pdf_is_a_failed_parse():
    with pytest.raises(DocumentReadError):
        await PdfTextLayerParser().parse(b"not a pdf", "broken.pdf")


def docling_answering(body: dict | None = None, status: int = 200) -> DoclingParser:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/documents/parse" and request.headers["authorization"] == "Bearer secret"
        return httpx.Response(status, json=body or {})

    return DoclingParser("http://parser:8080", "secret", 30, transport=httpx.MockTransport(respond))


async def test_docling_returns_markdown_tables_and_its_structured_form():
    parser = docling_answering(
        {
            "markdown": "| Net | 5,608.87 |",
            "page_count": 1,
            "tables": [{"page": 1, "rows": [["Net", "5,608.87"]]}],
            "pages": [{"page": 1, "markdown": "| Net | 5,608.87 |", "png_base64": base64.b64encode(b"PNG").decode()}],
            "structured": {"k": 1},
        }
    )

    parsed = await parser.parse(b"%PDF", "payslip.pdf")

    assert parsed.parser == "docling" and parsed.tables[0].rows == [["Net", "5,608.87"]] and parsed.structured == {"k": 1}
    assert parsed.pages[0].number == 1 and parsed.pages[0].image == b"PNG"


async def test_docling_errors_become_failed_parses():
    with pytest.raises(DocumentReadError, match="HTTP 503"):
        await docling_answering(status=503).parse(b"%PDF", "a.pdf")
    with pytest.raises(DocumentReadError, match="invalid response"):
        await docling_answering({"nope": 1}).parse(b"%PDF", "a.pdf")


def test_docling_is_only_used_where_a_service_is_configured(monkeypatch):
    monkeypatch.setattr("src.documents.parsers.settings.cli_runner_base_url", "")
    assert not any(p.name == "docling" for p in default_parsers())

    monkeypatch.setattr("src.documents.parsers.settings.cli_runner_base_url", "http://parser:8080")
    monkeypatch.setattr("src.documents.parsers.settings.cli_runner_shared_token", "secret")
    assert [p.name for p in default_parsers()] == ["text", "html", "docling", "pdf_text_layer"]


async def test_a_pdf_with_no_service_is_still_read_from_its_text_layer(monkeypatch):
    monkeypatch.setattr("src.documents.parsers.settings.cli_runner_base_url", "")

    parsed = await read_document(pdf_with_text("Net pay 5608.87"), "payslip.pdf")

    assert parsed.parser == "pdf_text_layer" and "5608.87" in parsed.markdown


def test_docling_tables_lose_their_column_padding():
    from src.documents.parsers import compact_tables

    padded = "Intro text\n\n| Item       |   Amount |\n|------------|----------|\n| Net pay    | 5,608.87 |\n"

    assert compact_tables(padded) == "Intro text\n\n| Item | Amount |\n| --- | --- |\n| Net pay | 5,608.87 |\n"
