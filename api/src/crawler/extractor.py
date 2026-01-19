"""
HTML content extractor for web pages.

This module fetches web pages and extracts clean, structured content
by converting HTML to Markdown for reliable text extraction.
"""

import httpx
from bs4 import BeautifulSoup, Tag
from markdownify import markdownify as md
from dataclasses import dataclass, field
from typing import Optional
import logging
import re

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

    def __post_init__(self):
        if not self.word_count and self.full_text:
            self.word_count = len(self.full_text.split())
        if not self.content_length and self.full_text:
            self.content_length = len(self.full_text)


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
    ):
        self.user_agent = user_agent
        self.timeout = timeout

    async def fetch_and_extract(self, url: str) -> ExtractedContent:
        """
        Fetch a URL and extract its content.

        Args:
            url: The URL to fetch

        Returns:
            ExtractedContent with the parsed content

        Raises:
            httpx.RequestError: If the request fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": self.user_agent},
            )
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                log.warning(f"Non-HTML content type for {url}: {content_type}")
                return ExtractedContent(url=url)

            html = response.text

        return self.extract(url, html)

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

        self._remove_noise(soup)

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

    def _remove_noise(self, soup: BeautifulSoup) -> None:
        """Remove scripts, styles, and common boilerplate elements."""
        for tag_name in self.REMOVE_TAGS:
            for element in soup.find_all(tag_name):
                element.decompose()

        for selector in self.BOILERPLATE_SELECTORS:
            try:
                for element in soup.select(selector):
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
