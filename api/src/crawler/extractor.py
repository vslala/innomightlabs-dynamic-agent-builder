"""
HTML content extractor for web pages.

This module fetches web pages and extracts clean, structured content
by converting HTML to Markdown for reliable text extraction.
"""

from bs4 import BeautifulSoup, NavigableString, Tag
from markdownify import markdownify as md
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from urllib.parse import urljoin
import httpx
import logging
import re
from src.crawler.page_fetch import PageFetch, fetch_page, same_site
from src.crawler.renderer import PageRenderer

log = logging.getLogger(__name__)


@dataclass
class ExtractedSection:
    """A section of extracted content with hierarchy info."""
    heading: Optional[str] = None
    heading_level: int = 0
    content: str = ""
    word_count: int = 0


@dataclass
class ExtractedContent:
    """Extracted content from a web page."""
    url: str
    title: str = ""
    description: str = ""
    full_text: str = ""
    sections: list[ExtractedSection] = field(default_factory=list)
    word_count: int = 0
    content_length: int = 0
    #: The address the page says is its own (`<link rel="canonical">`), made absolute; empty when it doesn't say.
    canonical_url: str = ""

    def __post_init__(self):
        if not self.word_count and self.full_text:
            self.word_count = len(self.full_text.split())
        if not self.content_length and self.full_text:
            self.content_length = len(self.full_text)


def decode_cloudflare_email(encoded: str) -> str:
    """The address Cloudflare's email obfuscation hid: the first byte is a key every other byte is XORed with.
    Empty when it isn't a valid encoding."""
    try:
        key = int(encoded[:2], 16)
        return "".join(chr(int(encoded[i:i + 2], 16) ^ key) for i in range(2, len(encoded), 2))
    except ValueError:
        return ""


#: Elements that run into the text beside them when their tags are dropped: "<a>Talk</a><a>to us</a>" is one word.
INLINE_TAGS = ["a", "button", "span", "strong", "b", "em", "i", "small", "label", "time"]
#: What may follow an inline element without a space: "<a>link</a>." stays "link.".
NO_SPACE_BEFORE = set(".,;:!?)]}%'’\"”")


class FetchOutcome(str, Enum):
    """What a page's fetch says about the page. Only `GONE` lets the crawler delete what it had of it."""

    OK = "ok"
    #: 304: it's what it was when its validators were given.
    NOT_MODIFIED = "not_modified"
    #: 404 or 410, or it now redirects to another site.
    GONE = "gone"
    #: Anything that doesn't prove the page is gone: a timeout, a 5xx, a 403, a page with no text, not HTML.
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
    """Extracts clean content from HTML pages using HTML-to-Markdown conversion."""

    REMOVE_TAGS = {"script", "style", "noscript", "iframe", "svg", "canvas"}

    BOILERPLATE_SELECTORS = [
        "nav",
        "footer",
        "header",
        "[role='navigation']",
        "[role='banner']",
        "[role='contentinfo']",
        ".sidebar",
        ".widget",
        ".advertisement",
        ".ads",
        ".social-share",
        ".share-buttons",
        ".comments",
        ".comment-form",
        ".breadcrumb",
        ".pagination",
        ".related-posts",
        "#sidebar",
        "#comments",
    ]

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
                read=lambda page: self.extract(page.url, page.html),
                is_empty=lambda content: not content.full_text.strip(),
            )
        except httpx.HTTPError as e:
            return Fetched(FetchOutcome.FAILED, url, reason=f"couldn't fetch it: {e.__class__.__name__}")
        return self._outcome(url, got)

    def _outcome(self, url: str, got: PageFetch[ExtractedContent]) -> Fetched:
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
            return Fetched(FetchOutcome.FAILED, page.url, reason=f"not HTML ({page.content_type or 'no content type'})")
        content = got.read
        if content is None or not content.full_text.strip():
            reason = "no text on the page" + (f" ({got.render_error})" if got.render_error else "")
            return Fetched(FetchOutcome.FAILED, page.url, reason=reason)
        return self._accepted(page.url, content, etag=page.etag, last_modified=page.last_modified)

    @staticmethod
    def _accepted(
        final_url: str, content: ExtractedContent, *, etag: Optional[str] = None, last_modified: Optional[str] = None
    ) -> Fetched:
        # The page's own address, when it says it's another one on this site: `/contact?topic=product` is `/contact`
        address = content.canonical_url if content.canonical_url and same_site(final_url, content.canonical_url) else final_url
        return Fetched(FetchOutcome.OK, address, content, etag=etag, last_modified=last_modified)

    def extract(self, url: str, html: str) -> ExtractedContent:
        """
        Extract content from HTML by converting to Markdown.

        Args:
            url: The source URL
            html: The HTML content

        Returns:
            ExtractedContent with the parsed content
        """
        soup = BeautifulSoup(html, "lxml")

        title = self._extract_title(soup)
        description = self._extract_description(soup)
        canonical_url = self._extract_canonical(soup, url)

        self._decode_emails(soup)
        self._remove_noise(soup)
        self._flatten_structure(soup)
        self._separate_inline(soup)

        main_content = self._find_main_content(soup)

        if main_content:
            markdown = self._html_to_markdown(main_content)
        else:
            body = soup.find("body")
            if body:
                markdown = self._html_to_markdown(body)
            else:
                markdown = ""

        markdown = self._clean_markdown(markdown)

        sections = self._split_into_sections(markdown)

        return ExtractedContent(
            url=url,
            title=title,
            description=description,
            full_text=markdown,
            sections=sections,
            word_count=len(markdown.split()),
            content_length=len(markdown),
            canonical_url=canonical_url,
        )

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract page title."""
        if soup.title and soup.title.string:
            return soup.title.string.strip()

        og_title = soup.find("meta", property="og:title")
        if og_title:
            content = og_title.get("content")
            if content and isinstance(content, str):
                return content.strip()

        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        return ""

    def _extract_description(self, soup: BeautifulSoup) -> str:
        """Extract page description."""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            content = meta_desc.get("content")
            if content and isinstance(content, str):
                return content.strip()

        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            content = og_desc.get("content")
            if content and isinstance(content, str):
                return content.strip()

        return ""

    def _extract_canonical(self, soup: BeautifulSoup, url: str) -> str:
        link = soup.find("link", rel="canonical")
        href = link.get("href") if isinstance(link, Tag) else None
        return urljoin(url, href.strip()) if isinstance(href, str) and href.strip() else ""

    def _decode_emails(self, soup: BeautifulSoup) -> None:
        """Put back the addresses Cloudflare hides behind "[email protected]", so the text says them."""
        for element in soup.select("[data-cfemail]"):
            address = decode_cloudflare_email(str(element.get("data-cfemail", "")))
            if address:
                element.string = address

    def _flatten_structure(self, soup: BeautifulSoup) -> None:
        """Rewrite markup that turns into confusing markdown into what it says.

        - A fact list (`<dl>` of terms and definitions) becomes one "term: definition" line each, not a term on one
          line and ": definition" on the next.
        - A list item with a heading in it is a card, not a bullet: it becomes a heading and its text, which makes the
          heading a section of its own instead of "- ### Heading".
        """
        for facts in soup.find_all("dl"):
            lines = soup.new_tag("div")
            for term in facts.find_all("dt"):
                definition = term.find_next_sibling("dd")
                line = soup.new_tag("p")
                line.string = f"{term.get_text(' ', strip=True)}: {definition.get_text(' ', strip=True) if definition else ''}".strip()
                lines.append(line)
            facts.replace_with(lines)
        for item in soup.find_all("li"):
            if item.find(["h1", "h2", "h3", "h4", "h5", "h6"]):
                item.unwrap()
        for group in soup.find_all(["ul", "ol"]):
            if not group.find("li"):
                group.unwrap()

    def _separate_inline(self, soup: BeautifulSoup) -> None:
        """Keep neighbouring inline elements and text apart once their tags are gone."""
        for element in soup.find_all(INLINE_TAGS):
            text = element.get_text()
            following = element.next_sibling
            beside = following.get_text() if isinstance(following, Tag) else str(following) if isinstance(following, NavigableString) else ""
            if text and beside and not text[-1].isspace() and not beside[0].isspace() and beside[0] not in NO_SPACE_BEFORE:
                element.insert_after(" ")

    def _remove_noise(self, soup: BeautifulSoup) -> None:
        """Remove scripts, styles, and common boilerplate elements."""
        for tag_name in self.REMOVE_TAGS:
            for element in soup.find_all(tag_name):
                element.decompose()

        for selector in self.BOILERPLATE_SELECTORS:
            try:
                for element in soup.select(selector):
                    if element.name == "header" and element.find_parent(["main", "article"]):
                        continue  # a section's heading, not the site's header
                    if not self._is_main_content(element):
                        element.decompose()
            except Exception:
                pass

    def _is_main_content(self, element: Tag) -> bool:
        """Check if element is or contains the main content area."""
        if element.name in ("main", "article"):
            return True
        if element.find("main") or element.find("article"):
            return True
        classes_attr = element.get("class")
        if classes_attr and isinstance(classes_attr, list):
            class_str = " ".join(str(c) for c in classes_attr).lower()
            if any(c in class_str for c in ["content", "post", "entry", "article"]):
                return True
        return False

    def _find_main_content(self, soup: BeautifulSoup) -> Optional[Tag]:
        """Find the main content area of the page."""
        if soup is None:
            return None

        main = soup.find("main")
        if main:
            return main

        article = soup.find("article")
        if article:
            return article

        for selector in [
            "[role='main']",
            ".post-content",
            ".entry-content",
            ".article-content",
            ".content",
            "#content",
            ".post",
            ".entry",
        ]:
            try:
                element = soup.select_one(selector)
                if element:
                    return element
            except Exception:
                pass

        return soup.find("body")

    def _html_to_markdown(self, element: Tag) -> str:
        """Convert HTML element to Markdown."""
        html_str = str(element)
        markdown = md(
            html_str,
            heading_style="ATX",
            bullets="-",
            strip=["a", "img"],
            newline_style="backslash",
        )
        return markdown

    def _clean_markdown(self, text: str) -> str:
        """Clean up the extracted markdown text."""
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        lines = text.split("\n")
        cleaned_lines = [line.strip() for line in lines]
        text = "\n".join(cleaned_lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()
        return text

    def _split_into_sections(self, markdown: str) -> list[ExtractedSection]:
        """Split markdown into sections based on headings."""
        if not markdown:
            return []

        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(heading_pattern.finditer(markdown))

        if not matches:
            return [ExtractedSection(
                content=markdown,
                word_count=len(markdown.split()),
            )]

        sections = []

        if matches[0].start() > 0:
            intro_content = markdown[:matches[0].start()].strip()
            if intro_content:
                sections.append(ExtractedSection(
                    content=intro_content,
                    word_count=len(intro_content.split()),
                ))

        for i, match in enumerate(matches):
            heading_level = len(match.group(1))
            heading_text = match.group(2).strip()

            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)

            content = markdown[start:end].strip()

            sections.append(ExtractedSection(
                heading=heading_text,
                heading_level=heading_level,
                content=content,
                word_count=len(content.split()),
            ))

        return sections
