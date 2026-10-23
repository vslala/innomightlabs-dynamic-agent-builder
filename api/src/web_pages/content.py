"""HTML as Markdown: a web page's main content for the crawler, and a CMS post's body for skills.

`extract_content` drops scripts, styles and site chrome (navigation, footers, sidebars, comments), finds the main
content, converts it to Markdown and splits it into sections by heading. `fragment_to_markdown` converts HTML that is
already the content, such as WordPress's `content.rendered`, the same way, without looking for the main part.
"""

import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag
from markdownify import markdownify as md


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


def extract_content(url: str, html: str) -> ExtractedContent:
    """The page's title, description, canonical address and main content as Markdown, split into sections."""
    soup = BeautifulSoup(html, "lxml")

    title = _extract_title(soup)
    description = _extract_description(soup)
    canonical_url = _extract_canonical(soup, url)

    _decode_emails(soup)
    _remove_tags(soup)
    _remove_boilerplate(soup)
    _flatten_structure(soup)
    _separate_inline(soup)

    main_content = _find_main_content(soup)

    if main_content:
        markdown = _html_to_markdown(main_content)
    else:
        body = soup.find("body")
        if body:
            markdown = _html_to_markdown(body)
        else:
            markdown = ""

    markdown = _clean_markdown(markdown)

    sections = _split_into_sections(markdown)

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


def fragment_to_markdown(html: str) -> str:
    """Markdown of HTML that is all content (a post's body): scripts and styles dropped, nothing else selected away."""
    soup = BeautifulSoup(html, "lxml")
    _decode_emails(soup)
    _remove_tags(soup)
    _flatten_structure(soup)
    _separate_inline(soup)
    body = soup.find("body")
    return _clean_markdown(_html_to_markdown(body)) if body else ""


def _extract_title(soup: BeautifulSoup) -> str:
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


def _extract_description(soup: BeautifulSoup) -> str:
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


def _extract_canonical(soup: BeautifulSoup, url: str) -> str:
    link = soup.find("link", rel="canonical")
    href = link.get("href") if isinstance(link, Tag) else None
    return urljoin(url, href.strip()) if isinstance(href, str) and href.strip() else ""


def _decode_emails(soup: BeautifulSoup) -> None:
    """Put back the addresses Cloudflare hides behind "[email protected]", so the text says them."""
    for element in soup.select("[data-cfemail]"):
        address = decode_cloudflare_email(str(element.get("data-cfemail", "")))
        if address:
            element.string = address


def _flatten_structure(soup: BeautifulSoup) -> None:
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


def _separate_inline(soup: BeautifulSoup) -> None:
    """Keep neighbouring inline elements and text apart once their tags are gone."""
    for element in soup.find_all(INLINE_TAGS):
        text = element.get_text()
        following = element.next_sibling
        beside = following.get_text() if isinstance(following, Tag) else str(following) if isinstance(following, NavigableString) else ""
        if text and beside and not text[-1].isspace() and not beside[0].isspace() and beside[0] not in NO_SPACE_BEFORE:
            element.insert_after(" ")


def _remove_tags(soup: BeautifulSoup) -> None:
    """Remove scripts, styles and embeds: markup that is never text."""
    for tag_name in REMOVE_TAGS:
        for element in soup.find_all(tag_name):
            element.decompose()


def _remove_boilerplate(soup: BeautifulSoup) -> None:
    """Remove the site's chrome: navigation, header, footer, sidebars, comments."""
    for selector in BOILERPLATE_SELECTORS:
        try:
            for element in soup.select(selector):
                if element.name == "header" and element.find_parent(["main", "article"]):
                    continue  # a section's heading, not the site's header
                if not _is_main_content(element):
                    element.decompose()
        except Exception:
            pass


def _is_main_content(element: Tag) -> bool:
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


def _find_main_content(soup: BeautifulSoup) -> Optional[Tag]:
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


def _html_to_markdown(element: Tag) -> str:
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


def _clean_markdown(text: str) -> str:
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


def _split_into_sections(markdown: str) -> list[ExtractedSection]:
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
