"""A page that looks empty to a plain fetch is read in a browser, when there is one to ask."""

import httpx
import pytest

from src.crawler.extractor import ContentExtractor, FetchOutcome
from src.crawler.renderer import BrowserRenderError, PageRenderer, RenderedPage, configured_page_renderer

URL = "https://example.com/pricing"
SHELL = '<html><head><title>App</title></head><body><div id="root"></div></body></html>'
PAINTED = "<html><head><title>Pricing</title></head><body><main><p>Seats cost ten pounds a month.</p></main></body></html>"


class FakeRenderer:
    def __init__(self, page: RenderedPage | None = None, error: BrowserRenderError | None = None):
        self.page, self.error, self.rendered = page, error, []

    async def render(self, url: str, *, user_agent: str) -> RenderedPage:
        self.rendered.append(url)
        if self.error:
            raise self.error
        return self.page or RenderedPage(final_url=url, status=200, html=PAINTED)


def site_answering(monkeypatch, body: str, headers: dict[str, str] | None = None) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/html", **(headers or {})})

    monkeypatch.setattr(
        "src.crawler.page_fetch.outbound.async_client", lambda **_: httpx.AsyncClient(transport=httpx.MockTransport(respond))
    )


async def test_an_empty_shell_is_read_as_the_browser_paints_it(monkeypatch):
    site_answering(monkeypatch, SHELL)
    renderer = FakeRenderer()

    fetched = await ContentExtractor(renderer=renderer).fetch(URL)

    assert fetched.outcome is FetchOutcome.OK and renderer.rendered == [URL]
    assert fetched.content is not None and "ten pounds" in fetched.content.full_text


async def test_a_rendered_page_keeps_no_validators_so_the_next_crawl_renders_it_again(monkeypatch):
    site_answering(monkeypatch, SHELL, {"etag": '"shell-v1"', "last-modified": "Sat, 17 Oct 2026 09:00:00 GMT"})

    fetched = await ContentExtractor(renderer=FakeRenderer()).fetch(URL)

    assert (fetched.etag, fetched.last_modified) == (None, None)


async def test_a_page_with_text_never_asks_the_browser(monkeypatch):
    site_answering(monkeypatch, PAINTED)
    renderer = FakeRenderer()

    fetched = await ContentExtractor(renderer=renderer).fetch(URL)

    assert fetched.outcome is FetchOutcome.OK and renderer.rendered == []


async def test_without_a_renderer_an_empty_shell_is_a_failed_read(monkeypatch):
    site_answering(monkeypatch, SHELL)

    fetched = await ContentExtractor().fetch(URL)

    assert fetched.outcome is FetchOutcome.FAILED and fetched.reason == "no text on the page"


async def test_a_browser_that_fails_leaves_the_page_a_failed_read(monkeypatch):
    site_answering(monkeypatch, SHELL)
    renderer = FakeRenderer(error=BrowserRenderError("the browser service is unreachable: ConnectError"))

    fetched = await ContentExtractor(renderer=renderer).fetch(URL)

    assert fetched.outcome is FetchOutcome.FAILED
    assert fetched.reason.startswith("no text on the page") and "unreachable" in fetched.reason


async def test_a_page_still_empty_in_the_browser_is_a_failed_read(monkeypatch):
    site_answering(monkeypatch, SHELL)
    renderer = FakeRenderer(RenderedPage(final_url=URL, status=200, html=SHELL))

    fetched = await ContentExtractor(renderer=renderer).fetch(URL)

    assert fetched.outcome is FetchOutcome.FAILED and "even in a browser" in fetched.reason


@pytest.mark.parametrize("final_url, status, why", [
    ("https://login.elsewhere.example/sso", 200, "sends a browser to"),
    (URL, 404, "HTTP 404 in the browser"),
])
async def test_a_page_that_leaves_the_site_or_errors_in_the_browser_is_failed_not_gone(monkeypatch, final_url, status, why):
    site_answering(monkeypatch, SHELL)
    renderer = FakeRenderer(RenderedPage(final_url=final_url, status=status, html=PAINTED))

    fetched = await ContentExtractor(renderer=renderer).fetch(URL)

    # Only the plain fetch may say a page is gone: a browser failure must never delete what the crawler already has.
    assert fetched.outcome is FetchOutcome.FAILED and why in fetched.reason


async def test_the_runner_is_asked_with_the_token_and_the_crawlers_name():
    sent: list[httpx.Request] = []

    def runner(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"final_url": URL, "status": 200, "html": PAINTED})

    page = await PageRenderer("http://runner:8080/", "secret", 20, httpx.MockTransport(runner)).render(URL, user_agent="Bot/1")

    assert page == RenderedPage(URL, 200, PAINTED)
    assert str(sent[0].url) == "http://runner:8080/v1/browser/render"
    assert sent[0].headers["authorization"] == "Bearer secret"
    assert sent[0].read() == b'{"url":"https://example.com/pricing","timeout_seconds":20,"user_agent":"Bot/1"}'


@pytest.mark.parametrize("answer", [
    httpx.Response(502, json={"detail": "couldn't load the page: net::ERR_FAILED"}),
    httpx.Response(401, json={"detail": "Invalid bearer token"}),
    httpx.Response(200, text="not json"),
])
async def test_a_runner_that_cant_render_raises_a_render_error(answer):
    renderer = PageRenderer("http://runner:8080", "secret", 20, httpx.MockTransport(lambda request: answer))

    with pytest.raises(BrowserRenderError):
        await renderer.render(URL, user_agent="Bot/1")


async def test_an_unreachable_runner_raises_a_render_error():
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(BrowserRenderError, match="unreachable"):
        await PageRenderer("http://runner:8080", "secret", 20, httpx.MockTransport(down)).render(URL, user_agent="Bot/1")


@pytest.mark.parametrize("fallback, base_url, token, expected", [
    (True, "http://runner:8080", "secret", True),
    (False, "http://runner:8080", "secret", False),
    (True, "", "secret", False),
    (True, "http://runner:8080", "", False),
])
def test_the_fallback_needs_the_setting_and_a_runner(monkeypatch, fallback, base_url, token, expected):
    from src.config.settings import settings

    monkeypatch.setattr(settings, "crawler_browser_fallback", fallback)
    monkeypatch.setattr(settings, "cli_runner_base_url", base_url)
    monkeypatch.setattr(settings, "cli_runner_shared_token", token)

    assert (configured_page_renderer() is not None) is expected
