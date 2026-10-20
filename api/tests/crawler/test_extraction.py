"""What the extractor makes of markup like innomight.com's: the page's own words, nothing missing or run together.

The snippets are trimmed from the real pages (each class name is the site's build output, kept as it was).
"""

import httpx
import pytest

from src.crawler.extractor import ContentExtractor, decode_cloudflare_email
from tests.crawler.fakes import read_response

URL = "https://example.com/software/bidsignal"


def page(body: str, head: str = "") -> str:
    return f"<html><head><title>BidSignal</title>{head}</head><body><nav><a href='/'>Home</a></nav><main>{body}</main><footer>Legal</footer></body></html>"


def text(body: str, head: str = "") -> str:
    return ContentExtractor().extract(URL, page(body, head)).full_text


def test_a_section_heading_inside_a_header_is_kept():
    out = text(
        '<section><header class="_header_1hq3h_18"><div><p class="_eyebrow">Features</p>'
        '<h2 id="features-title">Why teams choose BidSignal</h2></div></header><p>Rank notices by fit.</p></section>'
    )

    assert "## Why teams choose BidSignal" in out and "Features" in out and "Rank notices by fit." in out


def test_the_sites_own_header_footer_and_navigation_are_still_left_out():
    out = text("<p>Rank notices by fit.</p>")

    assert "Home" not in out and "Legal" not in out


def test_an_email_hidden_by_cloudflare_is_put_back():
    out = text(
        '<p>or email <a href="/cdn-cgi/l/email-protection#b2dad7dededdf2dbdcdcdddfdbd5dac69cd1dddf">'
        '<span class="__cf_email__" data-cfemail="b2dad7dededdf2dbdcdcdddfdbd5dac69cd1dddf">[email&#160;protected]</span></a></p>'
    )

    assert "hello@innomight.com" in out and "protected" not in out


def test_cloudflares_encoding_is_decoded_and_a_bad_one_gives_nothing():
    assert decode_cloudflare_email("b2dad7dededdf2dbdcdcdddfdbd5dac69cd1dddf") == "hello@innomight.com"
    assert decode_cloudflare_email("not hex") == "" and decode_cloudflare_email("") == ""


def test_neighbouring_links_and_labels_are_not_run_into_one_word():
    out = text(
        '<p><a href="/a">Visit bidsignal.innomightlabs.com</a><a href="/b">Talk to us</a></p>'
        '<div><span class="badge">Beta</span><span>by <!-- -->Innomight Labs Ltd</span></div>'
        '<p><a href="/c">Start a conversation</a><span>or email us</span></p>'
    )

    assert "Visit bidsignal.innomightlabs.com Talk to us" in out
    assert "Beta by Innomight Labs Ltd" in out
    assert "Start a conversation or email us" in out


def test_punctuation_after_a_link_stays_against_it():
    assert "see our pricing, then ask." in text('<p>see <a href="/p">our pricing</a>, then ask.</p>')


def test_a_fact_list_reads_as_label_and_value():
    out = text(
        '<dl><div><dt>Registered name</dt><dd>Innomight Labs Ltd</dd></div>'
        '<div><dt>Based in</dt><dd>United Kingdom</dd></div></dl>'
    )

    assert "Registered name: Innomight Labs Ltd" in out and "Based in: United Kingdom" in out


def test_a_card_in_a_list_becomes_a_heading_and_its_text():
    out = text(
        '<ul><li class="_feature"><span class="_icon"><svg><path d="m5 12"></path></svg></span>'
        '<h3>Opportunities that fit</h3><p>Describe your capabilities once.</p></li>'
        '<li class="_feature"><h3>Qualify in minutes</h3><p>Key requirements are pulled out.</p></li></ul>'
    )

    assert "### Opportunities that fit\n\nDescribe your capabilities once." in out
    assert "### Qualify in minutes" in out and "- ###" not in out


def test_a_plain_bulleted_list_stays_a_list():
    out = text("<ul><li>Fast</li><li>Cheap</li></ul>")

    assert "- Fast" in out and "- Cheap" in out


def test_each_heading_of_a_card_list_is_a_section():
    sections = ContentExtractor().extract(URL, page(
        "<h2>Why teams choose us</h2><ul><li><h3>Fit</h3><p>Ranked.</p></li><li><h3>Speed</h3><p>Quick.</p></li></ul>"
    )).sections

    assert [s.heading for s in sections] == ["Why teams choose us", "Fit", "Speed"]


@pytest.mark.parametrize(("canonical", "expected"), [
    ('<link rel="canonical" href="https://example.com/contact">', "https://example.com/contact"),
    ('<link rel="canonical" href="/contact">', "https://example.com/contact"),
    ("", ""),
])
def test_the_pages_own_address_is_read_from_its_canonical_link(canonical, expected):
    assert ContentExtractor().extract(URL, page("<p>Hi</p>", canonical)).canonical_url == expected


def test_a_page_that_says_its_another_page_on_the_site_is_read_as_that_page():
    html = page("<p>Seats cost ten pounds.</p>", '<link rel="canonical" href="https://example.com/contact">')
    response = httpx.Response(200, text=html, headers={"content-type": "text/html"},
                              request=httpx.Request("GET", "https://example.com/contact?topic=product"))

    fetched = read_response("https://example.com/contact?topic=product", response)

    assert fetched.url == "https://example.com/contact"


def test_a_canonical_link_to_another_site_is_ignored():
    html = page("<p>Seats cost ten pounds.</p>", '<link rel="canonical" href="https://elsewhere.example/post">')
    response = httpx.Response(200, text=html, headers={"content-type": "text/html"}, request=httpx.Request("GET", URL))

    assert read_response(URL, response).url == URL
