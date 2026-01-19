"""
Robots.txt parser for respecting website crawl policies.

This module fetches and parses robots.txt files to determine
which URLs are allowed or disallowed for crawling.
"""

import httpx
from urllib.parse import urlparse, urljoin
from dataclasses import dataclass, field
from typing import Optional
import logging
import re

log = logging.getLogger(__name__)


@dataclass
class RobotsRule:
    """A single rule from robots.txt."""
    path: str
    allowed: bool


@dataclass
class RobotsTxt:
    """Parsed robots.txt file."""
    rules: list[RobotsRule] = field(default_factory=list)
    crawl_delay: Optional[float] = None
    sitemaps: list[str] = field(default_factory=list)

    def is_allowed(self, path: str) -> bool:
        """
        Check if a path is allowed for crawling.

        Args:
            path: The URL path to check (e.g., "/products/item1")

        Returns:
            True if crawling is allowed, False otherwise
        """
        # Normalize path
        if not path.startswith("/"):
            path = "/" + path

        # Find the most specific matching rule
        best_match: Optional[RobotsRule] = None
        best_match_len = 0

        for rule in self.rules:
            if self._path_matches(path, rule.path):
                # Use the longest (most specific) matching rule
                if len(rule.path) > best_match_len:
                    best_match = rule
                    best_match_len = len(rule.path)

        # If no rule matches, default to allowed
        if best_match is None:
            return True

        return best_match.allowed

    def _path_matches(self, path: str, pattern: str) -> bool:
        """Check if a path matches a robots.txt pattern."""
        # Convert robots.txt pattern to regex
        # * matches any sequence of characters
        # $ at end means exact match
        regex_pattern = ""
        i = 0
        while i < len(pattern):
            c = pattern[i]
            if c == "*":
                regex_pattern += ".*"
            elif c == "$" and i == len(pattern) - 1:
                regex_pattern += "$"
            else:
                regex_pattern += re.escape(c)
            i += 1

        # If pattern doesn't end with $, it's a prefix match
        if not pattern.endswith("$"):
            regex_pattern += ".*"

        try:
            return bool(re.match(regex_pattern, path))
        except re.error:
            # If regex is invalid, fall back to prefix matching
            return path.startswith(pattern.rstrip("*$"))


class RobotsParser:
    """Parser for robots.txt files."""

    def __init__(self, user_agent: str = "*"):
        """
        Initialize the robots parser.

        Args:
            user_agent: The user agent to match rules for (default: "*")
        """
        self.user_agent = user_agent
        self._cache: dict[str, RobotsTxt] = {}

    async def fetch_and_parse(self, base_url: str, timeout: float = 10.0) -> RobotsTxt:
        """
        Fetch and parse robots.txt for a given base URL.

        Args:
            base_url: The base URL of the website (e.g., "https://example.com")
            timeout: Request timeout in seconds

        Returns:
            Parsed RobotsTxt object
        """
        # Normalize base URL
        parsed = urlparse(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        # Check cache
        if robots_url in self._cache:
            return self._cache[robots_url]

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    robots_url,
                    timeout=timeout,
                    follow_redirects=True,
                    headers={"User-Agent": f"InnomightLabsCrawler/1.0 (+https://innomightlabs.com)"},
                )

                if response.status_code == 200:
                    robots = self._parse(response.text)
                else:
                    # If robots.txt doesn't exist or returns error, allow all
                    log.info(f"robots.txt returned {response.status_code} for {robots_url}, allowing all")
                    robots = RobotsTxt()

        except httpx.RequestError as e:
            log.warning(f"Failed to fetch robots.txt from {robots_url}: {e}")
            # On error, allow all (fail open)
            robots = RobotsTxt()

        # Cache the result
        self._cache[robots_url] = robots
        return robots

    def _parse(self, content: str) -> RobotsTxt:
        """
        Parse robots.txt content.

        Args:
            content: The raw robots.txt content

        Returns:
            Parsed RobotsTxt object
        """
        robots = RobotsTxt()
        current_agents: list[str] = []
        in_relevant_section = False

        for line in content.split("\n"):
            # Remove comments and whitespace
            line = line.split("#")[0].strip()
            if not line:
                continue

            # Parse directive
            if ":" not in line:
                continue

            directive, value = line.split(":", 1)
            directive = directive.strip().lower()
            value = value.strip()

            if directive == "user-agent":
                # New user-agent section
                if current_agents and not in_relevant_section:
                    # Starting a new section, check if previous was relevant
                    pass
                current_agents = [value.lower()]
                in_relevant_section = (
                    value == "*" or
                    value.lower() == self.user_agent.lower() or
                    self.user_agent.lower() in value.lower()
                )

            elif in_relevant_section:
                if directive == "disallow":
                    if value:  # Empty disallow means allow all
                        robots.rules.append(RobotsRule(path=value, allowed=False))
                elif directive == "allow":
                    if value:
                        robots.rules.append(RobotsRule(path=value, allowed=True))
                elif directive == "crawl-delay":
                    try:
                        robots.crawl_delay = float(value)
                    except ValueError:
                        pass
                elif directive == "sitemap":
                    robots.sitemaps.append(value)

            elif directive == "sitemap":
                # Sitemap directives are global
                robots.sitemaps.append(value)

        return robots

    def is_allowed(self, url: str, robots: RobotsTxt) -> bool:
        """
        Check if a URL is allowed for crawling.

        Args:
            url: The full URL to check
            robots: The parsed RobotsTxt for the domain

        Returns:
            True if crawling is allowed
        """
        parsed = urlparse(url)
        path = parsed.path
        if parsed.query:
            path += "?" + parsed.query
        return robots.is_allowed(path)

    def clear_cache(self):
        """Clear the robots.txt cache."""
        self._cache.clear()
