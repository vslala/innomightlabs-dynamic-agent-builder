"""What a crawl learns from fetching a page: its content, or that it's unchanged, gone or unreadable this time.

The fetch is `src/web_pages/fetch.py` and the HTML-to-Markdown is `src/web_pages/content.py`; this module decides what
the answer means for the knowledge base.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import httpx
import logging
import os
from urllib.parse import unquote, urlparse

from src.config import settings
from src.documents.models import DocumentReadError
from src.documents.parsers import DOCUMENT_CONTENT_TYPES, extension
from src.documents.reader import parsers_for, read_document
from src.web_pages.content import ExtractedContent, extract_content
from src.web_pages.fetch import Page, PageFetch, fetch_page, same_site
from src.web_pages.renderer import PageRenderer

log = logging.getLogger(__name__)


class FetchOutcome(str, Enum):
    """What a page's fetch says about the page. Only `GONE` lets the crawler delete what it had of it."""

    OK = "ok"
    #: 304: it's what it was when its validators were given.
    NOT_MODIFIED = "not_modified"
    #: 404 or 410, or it now redirects to another site.
    GONE = "gone"
    #: Anything that doesn't prove the page is gone: a timeout, a 5xx, a 403, a page with no text, not HTML (and not a
    #: document that can be read).
    FAILED = "failed"


@dataclass(frozen=True)
class Fetched:
    outcome: FetchOutcome
    #: The page the content is from: the URL asked for, or the page on the same site it redirected to.
    url: str
    content: Optional[ExtractedContent] = None
    #: Why it isn't OK, for the run's log: "HTTP 404", "no text on the page".
    reason: str = ""
    #: The site's validators for what was read, to send back next time.
    etag: Optional[str] = None
    last_modified: Optional[str] = None


class ContentExtractor:
    """Fetches a page for the crawl and says what its answer means: content to index, unchanged, gone or failed."""

    def __init__(
        self,
        user_agent: str = "InnomightLabsCrawler/1.0 (+https://innomightlabs.com)",
        timeout: float = 30.0,
        renderer: Optional[PageRenderer] = None,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        #: Reads pages that a plain fetch finds empty. Without one, those pages fail as "no text on the page".
        self.renderer = renderer

    async def fetch(self, url: str, *, etag: Optional[str] = None, last_modified: Optional[str] = None) -> Fetched:
        """Fetch a page and extract its content, saying whether it's there, gone, or couldn't be read this time.

        Given the validators of the last read, a page that hasn't changed answers 304 and nothing is downloaded. A
        page with no text is read again as a browser shows it, when there is a renderer to ask.
        """
        headers = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        try:
            got = await fetch_page(
                url,
                user_agent=self.user_agent,
                timeout=self.timeout,
                headers=headers,
                renderer=self.renderer,
                read=lambda page: extract_content(page.url, page.html),
                is_empty=lambda content: not content.full_text.strip(),
            )
        except httpx.HTTPError as e:
            return Fetched(FetchOutcome.FAILED, url, reason=f"couldn't fetch it: {e.__class__.__name__}")
        return await self._outcome(url, got)

    async def _outcome(self, url: str, got: PageFetch[ExtractedContent]) -> Fetched:
        page = got.page
        if page.status == 304:
            return Fetched(FetchOutcome.NOT_MODIFIED, url)
        if page.status in (404, 410):
            return Fetched(FetchOutcome.GONE, url, reason=f"HTTP {page.status}")
        if not 200 <= page.status < 300:
            return Fetched(FetchOutcome.FAILED, url, reason=f"HTTP {page.status}")
        if not same_site(url, page.url):
            return Fetched(FetchOutcome.GONE, url, reason=f"moved to {page.url}")
        if "text/html" not in page.content_type:
            filename = document_filename(page)
            if filename:
                return await self._read_document(page, filename)
            return Fetched(FetchOutcome.FAILED, page.url, reason=f"not HTML ({page.content_type or 'no content type'})")
        content = got.read
        if content is None or not content.full_text.strip():
            reason = "no text on the page" + (f" ({got.render_error})" if got.render_error else "")
            return Fetched(FetchOutcome.FAILED, page.url, reason=reason)
        return self._accepted(page.url, content, etag=page.etag, last_modified=page.last_modified)

    async def _read_document(self, page: Page, filename: str) -> Fetched:
        """A PDF or Office file the site links to, read like an upload (`documents.read_document`) and indexed as the
        page at its address, so the crawl's ledger keeps it fresh and finds it gone like any page."""
        if len(page.body) > settings.document_max_bytes:
            return Fetched(FetchOutcome.FAILED, page.url, reason=f"the file is over {settings.document_max_bytes // (1024 * 1024)} MB")
        try:
            reading = await read_document(page.body, filename)
        except DocumentReadError as e:
            return Fetched(FetchOutcome.FAILED, page.url, reason=f"couldn't read the file: {e}")
        if not reading.markdown.strip():
            return Fetched(FetchOutcome.FAILED, page.url, reason="no text in the file")
        content = ExtractedContent(url=page.url, title=filename, full_text=reading.markdown)
        return self._accepted(page.url, content, etag=page.etag, last_modified=page.last_modified)

    @staticmethod
    def _accepted(
        final_url: str, content: ExtractedContent, *, etag: Optional[str] = None, last_modified: Optional[str] = None
    ) -> Fetched:
        # The page's own address, when it says it's another one on this site: `/contact?topic=product` is `/contact`
        address = content.canonical_url if content.canonical_url and same_site(final_url, content.canonical_url) else final_url
        return Fetched(FetchOutcome.OK, address, content, etag=etag, last_modified=last_modified)


def document_filename(page: Page) -> str:
    """The name to read a non-HTML answer as, when it is a document something can read; empty otherwise."""
    served_as = DOCUMENT_CONTENT_TYPES.get(page.content_type.split(";")[0].strip().lower(), "")
    name = os.path.basename(unquote(urlparse(page.url).path)) or "document"
    if served_as and extension(name) != served_as:
        name += served_as
    return name if (served_as or extension(name) in DOCUMENT_CONTENT_TYPES.values()) and parsers_for(name) else ""
