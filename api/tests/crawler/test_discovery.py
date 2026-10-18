"""Which URLs discovery offers a crawl: the site's pages, each once."""

import httpx
import pytest

from src.crawler.discovery import DiscoveryConfig, UrlCrawler

HOME = """<html><body>
<a href="/about">About</a> <a href="/about/">About again</a> <a href="/">Home</a> <a href="https://example.com">Home too</a>
<a href="/contact?topic=product">Contact</a> <a href="mailto:hello@example.com">Mail</a>
<a href="/cdn-cgi/l/email-protection#b2dad7">[email protected]</a> <a href="https://elsewhere.example/">Elsewhere</a>
</body></html>"""


@pytest.fixture
def crawler(monkeypatch):
    def serve(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=HOME, headers={"content-type": "text/html"})

    monkeypatch.setattr(
        "src.crawler.discovery.outbound.async_client", lambda **_: httpx.AsyncClient(transport=httpx.MockTransport(serve))
    )
    return UrlCrawler(DiscoveryConfig(respect_robots_txt=False))


async def discovered(crawler: UrlCrawler, start: str) -> list[str]:
    return [found.url async for found in crawler.discover(start)]


async def test_the_root_is_one_page_however_it_is_written(crawler):
    urls = await discovered(crawler, "https://example.com")

    assert urls.count("https://example.com/") == 1 and "https://example.com" not in urls


async def test_a_page_is_offered_once_with_or_without_a_trailing_slash(crawler):
    assert (await discovered(crawler, "https://example.com")).count("https://example.com/about") == 1


async def test_the_cdns_own_links_are_not_pages(crawler):
    urls = await discovered(crawler, "https://example.com")

    assert not any("/cdn-cgi/" in url for url in urls)


async def test_other_sites_and_mail_links_are_not_pages(crawler):
    urls = await discovered(crawler, "https://example.com")

    assert set(urls) == {"https://example.com/", "https://example.com/about", "https://example.com/contact?topic=product"}
