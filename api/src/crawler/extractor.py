"""
HTML content extractor for web pages.

This module fetches web pages and extracts clean, structured content
suitable for chunking and embedding.
"""

import httpx
from bs4 import BeautifulSoup, NavigableString, Tag
from dataclasses import dataclass, field
from typing import Optional
import logging
import re

log = logging.getLogger(__name__)


@dataclass
class ExtractedSection:
    """A section of extracted content with hierarchy info."""
    heading: Optional[str] = None
    heading_level: int = 0  # 0 = no heading, 1-6 = h1-h6
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
    """Extracts clean content from HTML pages."""

    # Tags to completely remove (including their content)
    REMOVE_TAGS = {
        "script", "style", "noscript", "iframe", "svg", "canvas",
        "nav", "footer", "header", "aside", "form", "button",
        "input", "select", "textarea", "label",
    }

    # Tags that typically contain navigation/boilerplate
    BOILERPLATE_CLASSES = {
        "nav", "navigation", "menu", "sidebar", "footer", "header",
        "breadcrumb", "pagination", "social", "share", "comment",
        "advertisement", "ad", "ads", "promo", "banner",
    }

    # Heading tags
    HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

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

            # Check content type
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                log.warning(f"Non-HTML content type for {url}: {content_type}")
                return ExtractedContent(url=url)

            html = response.text

        return self.extract(url, html)

    def extract(self, url: str, html: str) -> ExtractedContent:
        """
        Extract content from HTML.

        Args:
            url: The source URL
            html: The HTML content

        Returns:
            ExtractedContent with the parsed content
        """
        soup = BeautifulSoup(html, "lxml")

        # Extract metadata
        title = self._extract_title(soup)
        description = self._extract_description(soup)

        # Remove unwanted elements
        self._remove_unwanted(soup)

        # Find main content area
        main_content = self._find_main_content(soup)

        # Extract structured sections
        sections = self._extract_sections(main_content)

        # Build full text
        full_text = self._build_full_text(sections)

        return ExtractedContent(
            url=url,
            title=title,
            description=description,
            full_text=full_text,
            sections=sections,
            word_count=len(full_text.split()),
            content_length=len(full_text),
        )

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract page title."""
        # Try <title> tag
        if soup.title and soup.title.string:
            return soup.title.string.strip()

        # Try og:title
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            return og_title["content"].strip()

        # Try first h1
        h1 = soup.find("h1")
        if h1:
            return self._get_text(h1).strip()

        return ""

    def _extract_description(self, soup: BeautifulSoup) -> str:
        """Extract page description."""
        # Try meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            return meta_desc["content"].strip()

        # Try og:description
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            return og_desc["content"].strip()

        return ""

    def _remove_unwanted(self, soup: BeautifulSoup) -> None:
        """Remove unwanted elements from the soup."""
        # Remove by tag name
        for tag_name in self.REMOVE_TAGS:
            for element in soup.find_all(tag_name):
                element.decompose()

        # Collect elements to remove first (to avoid modifying while iterating)
        elements_to_remove = []
        for element in soup.find_all(True):
            if element.name is None:
                continue
            classes = element.get("class", []) or []
            element_id = element.get("id", "") or ""

            all_identifiers = " ".join(classes) + " " + element_id
            all_identifiers = all_identifiers.lower()

            for pattern in self.BOILERPLATE_CLASSES:
                if pattern in all_identifiers:
                    elements_to_remove.append(element)
                    break

        for element in elements_to_remove:
            try:
                element.decompose()
            except Exception:
                pass

    def _find_main_content(self, soup: BeautifulSoup) -> Optional[Tag]:
        """Find the main content area of the page."""
        if soup is None:
            return None

        # Try <main> tag
        main = soup.find("main")
        if main:
            return main

        # Try <article> tag
        article = soup.find("article")
        if article:
            return article

        # Try common content class names
        content_patterns = [
            {"class_": re.compile(r"(^|\s)(content|main|article|post|entry)(\s|$)", re.I)},
            {"id": re.compile(r"^(content|main|article|post|entry)$", re.I)},
            {"role": "main"},
        ]

        for pattern in content_patterns:
            element = soup.find("div", **pattern)
            if element:
                return element

        # Fall back to body
        body = soup.find("body")
        return body if body else soup

    def _extract_sections(self, element: Optional[Tag]) -> list[ExtractedSection]:
        """Extract content sections based on headings."""
        if element is None:
            return []

        sections: list[ExtractedSection] = []
        current_section = ExtractedSection()
        current_content: list[str] = []

        def flush_section():
            """Save current section if it has content."""
            nonlocal current_section, current_content
            content = " ".join(current_content).strip()
            content = self._clean_text(content)
            if content:
                current_section.content = content
                current_section.word_count = len(content.split())
                sections.append(current_section)
            current_section = ExtractedSection()
            current_content = []

        def process_element(elem):
            """Recursively process an element."""
            nonlocal current_section, current_content

            if isinstance(elem, NavigableString):
                text = str(elem).strip()
                if text:
                    current_content.append(text)
                return

            if not isinstance(elem, Tag):
                return

            if elem.name is None:
                return

            tag_name = elem.name.lower()

            # Check if this is a heading
            if tag_name in self.HEADING_TAGS:
                # Flush previous section
                flush_section()

                # Start new section with this heading
                heading_text = self._get_text(elem).strip()
                heading_level = int(tag_name[1])
                current_section.heading = heading_text
                current_section.heading_level = heading_level
                return

            # Process child elements
            for child in elem.children:
                process_element(child)

            # Add line breaks after block elements
            if tag_name in {"p", "div", "br", "li", "tr"}:
                current_content.append("\n")

        process_element(element)

        # Flush final section
        flush_section()

        # If no sections with headings, create one section with all content
        if not sections:
            full_text = self._get_text(element)
            full_text = self._clean_text(full_text)
            if full_text:
                sections.append(ExtractedSection(
                    content=full_text,
                    word_count=len(full_text.split()),
                ))

        return sections

    def _get_text(self, element: Tag) -> str:
        """Get text content from an element."""
        return element.get_text(separator=" ", strip=True)

    def _clean_text(self, text: str) -> str:
        """Clean extracted text."""
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)

        # Remove multiple newlines
        text = re.sub(r"\n\s*\n", "\n\n", text)

        # Strip leading/trailing whitespace
        text = text.strip()

        return text

    def _build_full_text(self, sections: list[ExtractedSection]) -> str:
        """Build full text from sections."""
        parts = []
        for section in sections:
            if section.heading:
                parts.append(f"## {section.heading}")
            if section.content:
                parts.append(section.content)
            parts.append("")  # Empty line between sections

        return "\n".join(parts).strip()
