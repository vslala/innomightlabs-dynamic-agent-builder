"""
URL discovery module for sitemap parsing and web crawling.

This module provides two discovery strategies:
1. Sitemap-based discovery: Parse XML sitemaps to find URLs
2. Crawl-based discovery: Start from a URL and follow links
"""

import httpx
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, urljoin, urldefrag
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional, Set
from bs4 import BeautifulSoup
import logging
import re

from src.crawler.robots import RobotsParser, RobotsTxt

log = logging.getLogger(__name__)


@dataclass
class DiscoveredUrl:
    """A discovered URL with metadata."""
    url: str
    depth: int = 0
    source: str = "sitemap"  # "sitemap" or "crawl"


@dataclass
class DiscoveryConfig:
    """Configuration for URL discovery."""
    max_pages: int = 100
    max_depth: int = 3
    respect_robots_txt: bool = True
    same_domain_only: bool = True
    rate_limit_ms: int = 1000
    timeout: float = 30.0
    user_agent: str = "InnomightLabsCrawler/1.0 (+https://innomightlabs.com)"


class SitemapParser:
    """Parser for XML sitemaps."""

    # XML namespaces used in sitemaps
    NAMESPACES = {
        "sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "image": "http://www.google.com/schemas/sitemap-image/1.1",
        "video": "http://www.google.com/schemas/sitemap-video/1.1",
        "news": "http://www.google.com/schemas/sitemap-news/0.9",
    }

    def __init__(self, config: DiscoveryConfig):
        self.config = config
        self._seen_urls: Set[str] = set()

    async def parse(self, sitemap_url: str) -> AsyncIterator[DiscoveredUrl]:
        """
        Parse a sitemap and yield discovered URLs.

        Handles both sitemap index files and regular sitemaps.

        Args:
            sitemap_url: URL of the sitemap

        Yields:
            DiscoveredUrl objects for each URL found
        """
        async for url in self._parse_sitemap(sitemap_url, depth=0):
            if len(self._seen_urls) >= self.config.max_pages:
                break
            yield url

    async def _parse_sitemap(self, sitemap_url: str, depth: int) -> AsyncIterator[DiscoveredUrl]:
        """Recursively parse sitemaps."""
        if depth > 10:  # Prevent infinite recursion
            log.warning(f"Sitemap recursion depth exceeded for {sitemap_url}")
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    sitemap_url,
                    timeout=self.config.timeout,
                    follow_redirects=True,
                    headers={"User-Agent": self.config.user_agent},
                )
                response.raise_for_status()
                content = response.text

        except httpx.RequestError as e:
            log.error(f"Failed to fetch sitemap {sitemap_url}: {e}")
            return

        # Try to parse as XML
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            log.error(f"Failed to parse sitemap XML {sitemap_url}: {e}")
            return

        # Get the root tag without namespace
        root_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

        if root_tag == "sitemapindex":
            # This is a sitemap index - recursively parse child sitemaps
            for sitemap in root.findall(".//sitemap:sitemap", self.NAMESPACES):
                loc = sitemap.find("sitemap:loc", self.NAMESPACES)
                if loc is not None and loc.text:
                    child_url = loc.text.strip()
                    log.info(f"Found child sitemap: {child_url}")
                    async for url in self._parse_sitemap(child_url, depth + 1):
                        yield url

            # Also try without namespace (some sitemaps don't use it)
            for sitemap in root.findall(".//sitemap"):
                loc = sitemap.find("loc")
                if loc is not None and loc.text:
                    child_url = loc.text.strip()
                    if child_url not in self._seen_urls:
                        log.info(f"Found child sitemap: {child_url}")
                        async for url in self._parse_sitemap(child_url, depth + 1):
                            yield url

        elif root_tag == "urlset":
            # This is a regular sitemap - extract URLs
            for url_elem in root.findall(".//sitemap:url", self.NAMESPACES):
                loc = url_elem.find("sitemap:loc", self.NAMESPACES)
                if loc is not None and loc.text:
                    url = loc.text.strip()
                    if url not in self._seen_urls:
                        self._seen_urls.add(url)
                        yield DiscoveredUrl(url=url, depth=0, source="sitemap")

            # Also try without namespace
            for url_elem in root.findall(".//url"):
                loc = url_elem.find("loc")
                if loc is not None and loc.text:
                    url = loc.text.strip()
                    if url not in self._seen_urls:
                        self._seen_urls.add(url)
                        yield DiscoveredUrl(url=url, depth=0, source="sitemap")


class UrlCrawler:
    """Crawl-based URL discovery by following links."""

    def __init__(self, config: DiscoveryConfig):
        self.config = config
        self.robots_parser = RobotsParser()
        self._seen_urls: Set[str] = set()
        self._queue: list[DiscoveredUrl] = []
        self._base_domain: str = ""
        self._robots: Optional[RobotsTxt] = None

    async def discover(self, start_url: str) -> AsyncIterator[DiscoveredUrl]:
        """
        Discover URLs by crawling from a starting URL.

        Args:
            start_url: The URL to start crawling from

        Yields:
            DiscoveredUrl objects for each URL found
        """
        # Parse base domain
        parsed = urlparse(start_url)
        self._base_domain = parsed.netloc

        # Fetch robots.txt if respecting it
        if self.config.respect_robots_txt:
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            self._robots = await self.robots_parser.fetch_and_parse(base_url)

        # Initialize queue with start URL
        normalized_start = self._normalize_url(start_url)
        self._seen_urls.add(normalized_start)
        self._queue.append(DiscoveredUrl(url=normalized_start, depth=0, source="crawl"))

        # Process queue
        while self._queue and len(self._seen_urls) <= self.config.max_pages:
            current = self._queue.pop(0)

            # Check depth limit
            if current.depth > self.config.max_depth:
                continue

            # Check robots.txt
            if self._robots and not self.robots_parser.is_allowed(current.url, self._robots):
                log.debug(f"Skipping {current.url} - disallowed by robots.txt")
                continue

            # Yield this URL
            yield current

            # Don't crawl deeper if at max depth
            if current.depth >= self.config.max_depth:
                continue

            # Fetch and extract links from this page
            try:
                links = await self._extract_links(current.url)
                for link in links:
                    if link not in self._seen_urls and len(self._seen_urls) < self.config.max_pages:
                        self._seen_urls.add(link)
                        self._queue.append(
                            DiscoveredUrl(url=link, depth=current.depth + 1, source="crawl")
                        )
            except Exception as e:
                log.warning(f"Failed to extract links from {current.url}: {e}")

    async def _extract_links(self, url: str) -> list[str]:
        """Extract links from a page."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    timeout=self.config.timeout,
                    follow_redirects=True,
                    headers={"User-Agent": self.config.user_agent},
                )
                response.raise_for_status()

                # Only process HTML content
                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type:
                    return []

                html = response.text

        except httpx.RequestError as e:
            log.debug(f"Failed to fetch {url} for link extraction: {e}")
            return []

        # Parse HTML and extract links
        soup = BeautifulSoup(html, "lxml")
        links: list[str] = []

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]

            # Skip empty, javascript, and mailto links
            if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue

            # Resolve relative URLs
            absolute_url = urljoin(url, href)

            # Normalize
            normalized = self._normalize_url(absolute_url)
            if not normalized:
                continue

            # Check if same domain
            if self.config.same_domain_only:
                parsed = urlparse(normalized)
                if parsed.netloc != self._base_domain:
                    continue

            links.append(normalized)

        return links

    def _normalize_url(self, url: str) -> str:
        """Normalize a URL for deduplication."""
        # Remove fragment
        url, _ = urldefrag(url)

        # Parse URL
        parsed = urlparse(url)

        # Only allow http and https
        if parsed.scheme not in ("http", "https"):
            return ""

        # Normalize path (remove trailing slash for non-root paths)
        path = parsed.path
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")

        # Reconstruct URL without fragment
        normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
        if parsed.query:
            normalized += f"?{parsed.query}"

        return normalized


class UrlDiscovery:
    """
    Unified URL discovery that supports both sitemap and crawl-based discovery.
    """

    def __init__(self, config: DiscoveryConfig):
        self.config = config
        self.robots_parser = RobotsParser()

    async def discover_from_sitemap(self, sitemap_url: str) -> AsyncIterator[DiscoveredUrl]:
        """
        Discover URLs from a sitemap.

        Args:
            sitemap_url: URL of the sitemap

        Yields:
            DiscoveredUrl objects
        """
        # Get base URL for robots.txt check
        parsed = urlparse(sitemap_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # Fetch robots.txt if respecting it
        robots: Optional[RobotsTxt] = None
        if self.config.respect_robots_txt:
            robots = await self.robots_parser.fetch_and_parse(base_url)

        parser = SitemapParser(self.config)
        count = 0

        async for url in parser.parse(sitemap_url):
            # Check robots.txt
            if robots and not self.robots_parser.is_allowed(url.url, robots):
                log.debug(f"Skipping {url.url} - disallowed by robots.txt")
                continue

            # Check same domain
            if self.config.same_domain_only:
                url_parsed = urlparse(url.url)
                if url_parsed.netloc != parsed.netloc:
                    continue

            yield url
            count += 1

            if count >= self.config.max_pages:
                break

    async def discover_from_url(self, start_url: str) -> AsyncIterator[DiscoveredUrl]:
        """
        Discover URLs by crawling from a starting URL.

        Args:
            start_url: The URL to start crawling from

        Yields:
            DiscoveredUrl objects
        """
        crawler = UrlCrawler(self.config)
        count = 0

        async for url in crawler.discover(start_url):
            yield url
            count += 1

            if count >= self.config.max_pages:
                break
