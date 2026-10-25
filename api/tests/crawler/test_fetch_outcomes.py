"""What a page's HTTP response says about the page: there, gone, or not readable this time."""

import httpx
import pytest

from src.crawler.extractor import ContentExtractor, FetchOutcome
from src.web_pages.fetch import same_site
from tests.crawler.fakes import read_response
from tests.documents_support import pdf_with_text

URL = "https://example.com/pricing"
PAGE = "<html><head><title>Pricing</title></head><body><main><p>Seats cost ten pounds a month.</p></main></body></html>"


def answered(status: int, *, body: str = PAGE, content_type: str = "text/html; charset=utf-8", at: str = URL):
    """The response a fetch of URL ended on: `at` is where redirects led."""
    return read_response(
        URL, httpx.Response(status, text=body, headers={"content-type": content_type}, request=httpx.Request("GET", at))
    )


def test_a_page_with_text_is_read():
    fetched = answered(200)

    assert fetched.outcome is FetchOutcome.OK and fetched.url == URL
    assert fetched.content is not None and "ten pounds" in fetched.content.full_text


@pytest.mark.parametrize("status", [404, 410])
def test_not_found_and_gone_say_the_page_is_gone(status):
    assert answered(status).outcome is FetchOutcome.GONE


@pytest.mark.parametrize("status", [500, 502, 503, 429, 403, 401])
def test_errors_that_dont_prove_anything_are_failures(status):
    fetched = answered(status)

    assert fetched.outcome is FetchOutcome.FAILED and fetched.reason == f"HTTP {status}"


def test_a_page_with_no_text_is_a_failed_read_not_an_empty_page():
    assert answered(200, body="<html><body><nav>Menu</nav></body></html>").outcome is FetchOutcome.FAILED


def test_a_page_that_isnt_html_or_a_document_is_a_failed_read():
    fetched = answered(200, body="PK", content_type="application/zip")

    assert fetched.outcome is FetchOutcome.FAILED and fetched.reason == "not HTML (application/zip)"


def test_a_linked_pdf_is_read_as_a_page(monkeypatch):
    monkeypatch.setattr("src.documents.parsers.settings.cli_runner_base_url", "")
    response = httpx.Response(200, content=pdf_with_text("Seats cost ten pounds"), headers={"content-type": "application/pdf"},
                              request=httpx.Request("GET", "https://example.com/files/price-list.pdf"))

    fetched = read_response("https://example.com/files/price-list.pdf", response)

    assert fetched.outcome is FetchOutcome.OK and fetched.url == "https://example.com/files/price-list.pdf"
    assert fetched.content.title == "price-list.pdf" and "ten pounds" in fetched.content.full_text


def test_a_document_that_cant_be_read_is_a_failed_read():
    fetched = answered(200, body="%PDF-1.7", content_type="application/pdf")

    assert fetched.outcome is FetchOutcome.FAILED and fetched.reason.startswith("couldn't read the file")


def test_a_redirect_within_the_site_reads_the_page_it_led_to():
    fetched = answered(200, at="https://www.example.com/plans")

    assert fetched.outcome is FetchOutcome.OK and fetched.url == "https://www.example.com/plans"


def test_a_redirect_to_another_site_says_the_page_is_gone():
    fetched = answered(200, at="https://elsewhere.example/pricing")

    assert fetched.outcome is FetchOutcome.GONE and "elsewhere.example" in fetched.reason


async def test_a_page_that_cant_be_reached_is_a_failed_read(monkeypatch):
    def time_out(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("too slow", request=request)

    monkeypatch.setattr(
        "src.web_pages.fetch.outbound.async_client", lambda **_: httpx.AsyncClient(transport=httpx.MockTransport(time_out))
    )

    fetched = await ContentExtractor().fetch(URL)

    assert fetched.outcome is FetchOutcome.FAILED and "ConnectTimeout" in fetched.reason


def test_a_site_and_its_www_are_one_site():
    assert same_site("https://example.com/a", "https://www.example.com/b")
    assert not same_site("https://example.com/a", "https://docs.example.com/a")


def test_not_modified_says_the_page_is_what_it_was():
    assert answered(304, body="").outcome is FetchOutcome.NOT_MODIFIED


def test_a_read_keeps_the_sites_validators():
    fetched = read_response(URL, httpx.Response(
        200, text=PAGE, request=httpx.Request("GET", URL),
        headers={"content-type": "text/html", "etag": '"v7"', "last-modified": "Sat, 17 Oct 2026 09:00:00 GMT"},
    ))

    assert (fetched.etag, fetched.last_modified) == ('"v7"', "Sat, 17 Oct 2026 09:00:00 GMT")


async def test_the_validators_of_the_last_read_are_sent_back(monkeypatch):
    sent: list[httpx.Headers] = []

    def not_modified(request: httpx.Request) -> httpx.Response:
        sent.append(request.headers)
        return httpx.Response(304)

    monkeypatch.setattr(
        "src.web_pages.fetch.outbound.async_client", lambda **_: httpx.AsyncClient(transport=httpx.MockTransport(not_modified))
    )

    fetched = await ContentExtractor().fetch(URL, etag='"v7"', last_modified="Sat, 17 Oct 2026 09:00:00 GMT")

    assert fetched.outcome is FetchOutcome.NOT_MODIFIED
    assert sent[0]["if-none-match"] == '"v7"' and sent[0]["if-modified-since"] == "Sat, 17 Oct 2026 09:00:00 GMT"
