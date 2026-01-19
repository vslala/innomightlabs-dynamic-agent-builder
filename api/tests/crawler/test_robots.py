"""
Unit tests for the robots.txt parser.
"""

import pytest
from src.crawler.robots import RobotsParser, RobotsTxt, RobotsRule


class TestRobotsRule:
    """Tests for RobotsRule dataclass."""

    def test_create_allow_rule(self):
        """Test creating an allow rule."""
        rule = RobotsRule(path="/allowed/", allowed=True)
        assert rule.path == "/allowed/"
        assert rule.allowed is True

    def test_create_disallow_rule(self):
        """Test creating a disallow rule."""
        rule = RobotsRule(path="/private/", allowed=False)
        assert rule.path == "/private/"
        assert rule.allowed is False


class TestRobotsTxt:
    """Tests for RobotsTxt class."""

    def test_empty_robots_allows_all(self):
        """Test that empty robots.txt allows all paths."""
        robots = RobotsTxt()
        assert robots.is_allowed("/any/path") is True
        assert robots.is_allowed("/another/path") is True

    def test_disallow_specific_path(self):
        """Test disallowing a specific path."""
        robots = RobotsTxt(rules=[
            RobotsRule(path="/private/", allowed=False),
        ])
        assert robots.is_allowed("/private/") is False
        assert robots.is_allowed("/private/secret") is False
        assert robots.is_allowed("/public/") is True

    def test_allow_specific_path(self):
        """Test allowing a specific path within disallowed section."""
        robots = RobotsTxt(rules=[
            RobotsRule(path="/", allowed=False),
            RobotsRule(path="/public/", allowed=True),
        ])
        assert robots.is_allowed("/private/") is False
        assert robots.is_allowed("/public/") is True
        assert robots.is_allowed("/public/page") is True

    def test_more_specific_rule_wins(self):
        """Test that more specific rules take precedence."""
        robots = RobotsTxt(rules=[
            RobotsRule(path="/", allowed=False),
            RobotsRule(path="/public/", allowed=True),
            RobotsRule(path="/public/admin/", allowed=False),
        ])
        assert robots.is_allowed("/public/") is True
        assert robots.is_allowed("/public/page") is True
        assert robots.is_allowed("/public/admin/") is False
        assert robots.is_allowed("/public/admin/page") is False

    def test_wildcard_pattern(self):
        """Test wildcard patterns in rules."""
        robots = RobotsTxt(rules=[
            RobotsRule(path="/*.pdf", allowed=False),
        ])
        assert robots.is_allowed("/docs/file.pdf") is False
        assert robots.is_allowed("/file.pdf") is False
        assert robots.is_allowed("/file.html") is True

    def test_exact_match_pattern(self):
        """Test exact match pattern with $."""
        robots = RobotsTxt(rules=[
            RobotsRule(path="/exact$", allowed=False),
        ])
        assert robots.is_allowed("/exact") is False
        assert robots.is_allowed("/exact/more") is True
        assert robots.is_allowed("/exactlynot") is True

    def test_path_normalization(self):
        """Test that paths are normalized."""
        robots = RobotsTxt(rules=[
            RobotsRule(path="/test/", allowed=False),
        ])
        # Should work with or without leading slash
        assert robots.is_allowed("test/") is False
        assert robots.is_allowed("/test/") is False

    def test_crawl_delay(self):
        """Test crawl delay storage."""
        robots = RobotsTxt(crawl_delay=2.5)
        assert robots.crawl_delay == 2.5

    def test_sitemaps(self):
        """Test sitemap storage."""
        robots = RobotsTxt(sitemaps=[
            "https://example.com/sitemap.xml",
            "https://example.com/sitemap2.xml",
        ])
        assert len(robots.sitemaps) == 2
        assert "https://example.com/sitemap.xml" in robots.sitemaps


class TestRobotsParser:
    """Tests for RobotsParser class."""

    @pytest.fixture
    def parser(self):
        """Create a default parser."""
        return RobotsParser()

    def test_parse_simple_robots(self, parser):
        """Test parsing simple robots.txt content."""
        content = """
User-agent: *
Disallow: /private/
Disallow: /admin/
Allow: /admin/public/
"""
        robots = parser._parse(content)
        assert len(robots.rules) == 3
        assert robots.is_allowed("/public/") is True
        assert robots.is_allowed("/private/") is False
        assert robots.is_allowed("/admin/") is False
        assert robots.is_allowed("/admin/public/") is True

    def test_parse_with_crawl_delay(self, parser):
        """Test parsing robots.txt with crawl-delay."""
        content = """
User-agent: *
Crawl-delay: 2
Disallow: /private/
"""
        robots = parser._parse(content)
        assert robots.crawl_delay == 2.0

    def test_parse_with_sitemaps(self, parser):
        """Test parsing robots.txt with sitemap directives."""
        content = """
User-agent: *
Disallow: /private/

Sitemap: https://example.com/sitemap.xml
Sitemap: https://example.com/sitemap-posts.xml
"""
        robots = parser._parse(content)
        assert len(robots.sitemaps) == 2
        assert "https://example.com/sitemap.xml" in robots.sitemaps

    def test_parse_comments_ignored(self, parser):
        """Test that comments are ignored."""
        content = """
# This is a comment
User-agent: *
Disallow: /private/ # Inline comment
# Another comment
Allow: /public/
"""
        robots = parser._parse(content)
        assert len(robots.rules) == 2

    def test_parse_specific_user_agent(self):
        """Test parsing with specific user agent."""
        parser = RobotsParser(user_agent="InnomightBot")
        content = """
User-agent: *
Disallow: /general/

User-agent: InnomightBot
Disallow: /specific/
Allow: /specific/allowed/
"""
        robots = parser._parse(content)
        # Should have rules from InnomightBot section
        assert any(r.path == "/specific/" for r in robots.rules)

    def test_parse_empty_content(self, parser):
        """Test parsing empty robots.txt."""
        robots = parser._parse("")
        assert len(robots.rules) == 0
        assert robots.is_allowed("/anything") is True

    def test_parse_malformed_content(self, parser):
        """Test parsing malformed robots.txt."""
        content = """
This is not valid robots.txt
No colons here
User-agent: *
Still no rules
Disallow: /valid/
"""
        robots = parser._parse(content)
        # Should parse what it can
        assert len(robots.rules) == 1
        assert robots.is_allowed("/valid/") is False

    def test_is_allowed_with_url(self, parser):
        """Test is_allowed with full URL."""
        robots = RobotsTxt(rules=[
            RobotsRule(path="/private/", allowed=False),
        ])
        assert parser.is_allowed("https://example.com/public/page", robots) is True
        assert parser.is_allowed("https://example.com/private/page", robots) is False

    def test_is_allowed_with_query_string(self, parser):
        """Test is_allowed with query string."""
        robots = RobotsTxt(rules=[
            RobotsRule(path="/search?", allowed=False),
        ])
        assert parser.is_allowed("https://example.com/search?q=test", robots) is False
        assert parser.is_allowed("https://example.com/search", robots) is True

    def test_cache_clear(self, parser):
        """Test cache clearing."""
        parser._cache["test"] = RobotsTxt()
        assert len(parser._cache) == 1
        parser.clear_cache()
        assert len(parser._cache) == 0


class TestRobotsTxtPatternMatching:
    """Tests for pattern matching edge cases."""

    def test_wildcard_at_start(self):
        """Test wildcard at start of pattern."""
        robots = RobotsTxt(rules=[
            RobotsRule(path="*private", allowed=False),
        ])
        assert robots.is_allowed("/some/private") is False
        assert robots.is_allowed("/private") is False

    def test_wildcard_in_middle(self):
        """Test wildcard in middle of pattern."""
        robots = RobotsTxt(rules=[
            RobotsRule(path="/docs/*.pdf", allowed=False),
        ])
        assert robots.is_allowed("/docs/test.pdf") is False
        assert robots.is_allowed("/docs/subdir/file.pdf") is False
        assert robots.is_allowed("/other/file.pdf") is True

    def test_multiple_wildcards(self):
        """Test multiple wildcards in pattern."""
        robots = RobotsTxt(rules=[
            RobotsRule(path="/*print*.html", allowed=False),
        ])
        assert robots.is_allowed("/docs/print-page.html") is False
        assert robots.is_allowed("/printable.html") is False
        assert robots.is_allowed("/docs/page.html") is True

    def test_complex_pattern(self):
        """Test complex pattern combining wildcards and exact match."""
        # Note: The pattern /articles/*?page=* matches any URL with ?page= in it
        # because the first * is greedy. The $ forces end-of-string match.
        robots = RobotsTxt(rules=[
            RobotsRule(path="/articles/*.html$", allowed=False),
        ])
        assert robots.is_allowed("/articles/test.html") is False
        assert robots.is_allowed("/articles/test.html?query=1") is True
        assert robots.is_allowed("/articles/test.htm") is True
