"""What chunks a page makes: each passage once, and nothing that's only a heading."""


from src.crawler.chunking import get_chunking_strategy
from src.crawler.extractor import ExtractedSection

URL = "https://example.com/about"
BODY = "We design, build and run software for clients and for ourselves, shipping small improvements often. "


def section(heading: str | None, content: str) -> ExtractedSection:
    return ExtractedSection(heading=heading, heading_level=2 if heading else 0, content=content, word_count=len(content.split()))


def chunk(sections: list[ExtractedSection]):
    text = "\n\n".join(f"## {s.heading}\n\n{s.content}" if s.heading else s.content for s in sections)
    return get_chunking_strategy("hierarchical").chunk(content=text, source_url=URL, page_title="About", sections=sections)


def texts(chunks, level: int) -> list[str]:
    return [" ".join(c.content.split()) for c in chunks if c.level == level]


def test_a_section_that_fits_in_one_chunk_is_stored_once():
    chunks = chunk([section("Our story", BODY * 2), section("Our team", BODY * 2)])

    assert len(texts(chunks, 1)) == 2
    assert texts(chunks, 2) == [], "the paragraph chunks would only repeat the sections"


def test_a_section_too_long_for_one_chunk_still_has_its_paragraphs():
    chunks = chunk([section("Our story", (BODY * 3 + "\n\n") * 8)])

    assert len(texts(chunks, 1)) == 1 and len(texts(chunks, 2)) > 1


def test_a_heading_with_no_body_joins_the_next_section_s_heading():
    chunks = chunk([section(None, "About us"), section("A digital agency", BODY * 2), section("Our story", BODY * 2)])

    sections = texts(chunks, 1)
    assert len(sections) == 2 and sections[0].startswith("Section: About us — A digital agency")
    assert not any(len(c.content.split()) <= 3 for c in chunks if c.level > 0), "no chunk of just a heading"


def test_an_eyebrow_before_text_with_no_heading_joins_its_text():
    chunks = chunk([section(None, "Contact"), section(None, BODY * 2)])

    [only] = texts(chunks, 1)
    assert only.startswith("Contact ") and "We design" in only


def test_a_tiny_last_section_joins_the_one_before():
    chunks = chunk([section("Our story", BODY * 2), section("Legal", "Terms apply")])

    [only] = texts(chunks, 1)
    assert "Our story" in only and "Terms apply" in only


def test_a_page_of_one_tiny_section_is_kept():
    chunks = chunk([section("Coming soon", "Check back")])

    assert texts(chunks, 1) == ["Section: Coming soon Check back"]


def test_a_chunk_carries_the_heading_of_its_section():
    chunks = chunk([section("Our story", BODY * 2), section("Our team", (BODY * 3 + "\n\n") * 8)])

    assert {c.section_heading for c in chunks if c.level > 0} == {"Our story", "Our team"}
    assert [c.section_heading for c in chunks if c.level == 0] == [""]
