"""The one way we fetch a web page, whether a caller reads the page's text or looks for the links on it.

The crawler reads pages and finds links with it.

A plain fetch of a React or Angular app returns an empty shell. What counts as empty depends on who is asking: no text
for the extractor, no links for URL discovery. Each caller says what it reads from a page and when that is empty, and a
page that reads empty is read again as a browser paints it, when there is a browser to ask.
"""

import logging
from dataclasses import dataclass
from typing import Callable, Generic, Optional, TypeVar
from urllib.parse import urlparse

import httpx

from src.common import outbound
from src.web_pages.renderer import BrowserRenderError, PageRenderer

log = logging.getLogger(__name__)

T = TypeVar("T")


def same_site(url: str, other: str) -> bool:
    """`example.com` and `www.example.com` are one site: sites redirect between them."""

    def host(value: str) -> str:
        return urlparse(value).netloc.lower().removeprefix("www.")

    return host(url) == host(other)


@dataclass(frozen=True)
class Page:
    #: Where the fetch ended up, after redirects.
    url: str
    status: int
    content_type: str
    #: The HTML, empty for anything that isn't HTML.
    html: str
    #: The site's validators for this fetch. A page read in a browser has none: see `fetch_page`.
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    #: The bytes of an answer that isn't HTML (a PDF a site links to), for a caller that reads files; empty for HTML.
    body: bytes = b""


@dataclass(frozen=True)
class PageFetch(Generic[T]):
    page: Page
    #: What the caller read from the page; None when there was nothing to read (an error, not HTML, another site).
    read: Optional[T]
    #: Why a page that read empty stayed that way, when a browser was asked and couldn't help.
    render_error: str = ""


def page_from_response(response: httpx.Response) -> Page:
    content_type = response.headers.get("content-type", "")
    return Page(
        url=str(response.url),
        status=response.status_code,
        content_type=content_type,
        html=response.text if "text/html" in content_type else "",
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
        body=b"" if "text/html" in content_type else response.content,
    )


def readable(asked_for: str, page: Page) -> bool:
    """Whether the page is an HTML page of the site that was asked for, worth reading."""
    return 200 <= page.status < 300 and "text/html" in page.content_type and same_site(asked_for, page.url)


async def fetch_page(
    url: str,
    *,
    user_agent: str,
    timeout: float,
    read: Callable[[Page], T],
    is_empty: Callable[[T], bool],
    headers: Optional[dict[str, str]] = None,
    renderer: Optional[PageRenderer] = None,
) -> PageFetch[T]:
    """Fetch a page and read it; when it reads empty, read what a browser shows instead.

    Raises `httpx.HTTPError` when the page can't be fetched. A browser that fails, or finds nothing either, leaves the
    plain fetch as the answer, with `render_error` saying why. A page the browser read has no validators: the shell's
    ETag doesn't change when the content it paints does, so keeping it would have every later crawl answer 304 and
    never render the page again.
    """
    async with outbound.async_client() as client:
        response = await client.get(
            url, timeout=timeout, follow_redirects=True, headers={"User-Agent": user_agent, **(headers or {})}
        )
    page = page_from_response(response)
    if not readable(url, page):
        return PageFetch(page, None)
    result = read(page)
    if renderer is None or not is_empty(result):
        return PageFetch(page, result)

    try:
        shown = await renderer.render(url, user_agent=user_agent)
    except BrowserRenderError as e:
        log.warning(f"Couldn't render {url} in a browser: {e}")
        return PageFetch(page, result, str(e))
    painted = Page(url=shown.final_url, status=shown.status, content_type="text/html", html=shown.html)
    if not same_site(url, painted.url):
        return PageFetch(page, result, f"the page sends a browser to {painted.url}")
    if not readable(url, painted):
        return PageFetch(page, result, f"HTTP {painted.status} in the browser")
    read_in_browser = read(painted)
    if is_empty(read_in_browser):
        return PageFetch(page, result, "empty even in a browser")
    return PageFetch(painted, read_in_browser)
