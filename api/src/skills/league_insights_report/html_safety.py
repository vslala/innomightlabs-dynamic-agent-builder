from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urlparse


class UnsafeHtmlError(ValueError):
    pass


BLOCKED_TAGS = {"script", "iframe", "object", "embed", "base", "form", "input", "button", "link"}
URL_ATTRS = {"href", "src", "xlink:href"}
HTML_FENCE_RE = re.compile(r"```(?:html)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
STYLE_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)


def extract_html_document(text: str) -> str:
    stripped = text.strip()
    fence = HTML_FENCE_RE.search(stripped)
    if fence:
        stripped = fence.group(1).strip()

    lower = stripped.lower()
    start = lower.find("<!doctype html")
    if start < 0:
        start = lower.find("<html")
    end = lower.rfind("</html>")
    if start < 0 or end < 0:
        raise UnsafeHtmlError("Generated report must be a complete HTML document")
    return stripped[start : end + len("</html>")].strip()


def validate_safe_report_html(html: str) -> None:
    parser = _ReportHtmlSafetyParser()
    parser.feed(html)
    parser.close()
    _validate_css(html)


class _ReportHtmlSafetyParser(HTMLParser):
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._validate_tag(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._validate_tag(tag, attrs)

    def _validate_tag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in BLOCKED_TAGS:
            raise UnsafeHtmlError(f"Generated report contains blocked <{normalized_tag}> tag")

        for raw_name, raw_value in attrs:
            name = raw_name.lower()
            value = (raw_value or "").strip()
            if name.startswith("on"):
                raise UnsafeHtmlError(f"Generated report contains blocked event handler attribute: {name}")
            if normalized_tag == "meta" and name == "http-equiv" and value.lower() == "refresh":
                raise UnsafeHtmlError("Generated report contains blocked meta refresh")
            if name in URL_ATTRS:
                _validate_url(value)
            if name == "style":
                _validate_css_block(value)


def _validate_url(value: str) -> None:
    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    if scheme in {"javascript", "http", "https"}:
        raise UnsafeHtmlError("Generated report contains blocked external or executable URL")
    if scheme == "data" and value.lower().startswith("data:text/html"):
        raise UnsafeHtmlError("Generated report contains blocked HTML data URL")


def _validate_css(html: str) -> None:
    for match in STYLE_RE.finditer(html):
        _validate_css_block(match.group(1))


def _validate_css_block(css_value: str) -> None:
    css = css_value.lower()
    if "@import" in css:
        raise UnsafeHtmlError("Generated report contains blocked CSS import")
    if re.search(r"url\(\s*['\"]?\s*(?:https?:|javascript:)", css):
        raise UnsafeHtmlError("Generated report contains blocked CSS URL")
