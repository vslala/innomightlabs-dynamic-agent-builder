"""Which URLs discovery offers a crawl: the site's pages, each once."""

import httpx
import pytest

from src.crawler.discovery import DiscoveryConfig, UrlCrawler
from src.crawler.renderer import BrowserRenderError, RenderedPage

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
        "src.crawler.page_fetch.outbound.async_client", lambda **_: httpx.AsyncClient(transport=httpx.MockTransport(serve))
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


SHELL = '<html><body><div id="root"></div></body></html>'
PAINTED_NAV = '<html><body><nav><a href="/pricing">Pricing</a> <a href="/docs">Docs</a></nav></body></html>'


class FakeRenderer:
    def __init__(self, html: str = PAINTED_NAV, error: BrowserRenderError | None = None):
        self.html, self.error, self.rendered = html, error, []

    async def render(self, url: str, *, user_agent: str) -> RenderedPage:
        self.rendered.append(url)
        if self.error:
            raise self.error
        return RenderedPage(final_url=url, status=200, html=self.html)


def site_serving(monkeypatch, html: str) -> None:
    monkeypatch.setattr(
        "src.crawler.page_fetch.outbound.async_client",
        lambda **_: httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text=html, headers={"content-type": "text/html"}))
        ),
    )


async def test_a_page_with_no_links_is_searched_for_links_as_a_browser_paints_it(monkeypatch):
    site_serving(monkeypatch, SHELL)
    renderer = FakeRenderer()

    urls = await discovered(UrlCrawler(DiscoveryConfig(respect_robots_txt=False, max_depth=1), renderer), "https://example.com")

    assert set(urls) == {"https://example.com/", "https://example.com/pricing", "https://example.com/docs"}
    assert renderer.rendered == ["https://example.com/"]


async def test_a_page_with_links_never_asks_the_browser(monkeypatch):
    site_serving(monkeypatch, HOME)
    renderer = FakeRenderer()

    await discovered(UrlCrawler(DiscoveryConfig(respect_robots_txt=False, max_depth=1), renderer), "https://example.com")

    assert renderer.rendered == []


async def test_a_browser_that_fails_leaves_a_page_with_no_links_as_it_was(monkeypatch):
    site_serving(monkeypatch, SHELL)
    renderer = FakeRenderer(error=BrowserRenderError("the browser service is unreachable: ConnectError"))

    urls = await discovered(UrlCrawler(DiscoveryConfig(respect_robots_txt=False, max_depth=1), renderer), "https://example.com")

    assert urls == ["https://example.com/"]
