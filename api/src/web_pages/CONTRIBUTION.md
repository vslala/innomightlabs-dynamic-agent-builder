# Contributing to `web_pages/`

Fetching a web page and reading HTML as Markdown. The crawler fetches and indexes pages with it, and skills convert
HTML they get from an API (`wordpress_search.read_post` reads a post's `content.rendered`), so both write the same
Markdown for the same markup.

```text
web_pages/
  fetch.py      fetch_page(url, read=, is_empty=, headers=, renderer=) -> PageFetch; Page, readable, same_site
  content.py    extract_content(url, html) -> ExtractedContent (title, description, canonical, Markdown, sections)
                fragment_to_markdown(html) -> str, for HTML that is already the content (no chrome to strip)
  renderer.py   PageRenderer: the page as headless Chromium paints it (infra CLI runner); configured_page_renderer()
```

## Conventions

- **One way to fetch a page.** `fetch_page` goes through `common.outbound` (public destinations only, every redirect
  checked), follows redirects, and reads only a 2xx HTML page of the site asked for (`readable`). Callers decide what
  an empty read means and whether to pass a renderer. Don't open another client for a page fetch.
- **`same_site` treats `example.com` and `www.example.com` as one site**, because sites redirect between them.
- **Use the right entry point.** `extract_content` is for a whole page: it strips the site's chrome and picks the main
  content, which can cut parts of a fragment. `fragment_to_markdown` only drops scripts and styles.
- **Extraction is the crawler's reader.** Changing `content.py` changes what knowledge bases hold: bump
  `READER_VERSION` in `crawler/page_chunks.py` so crawled pages are read again.
- No domain logic here: what a 404 or an empty page means belongs to the caller (see `crawler/extractor.py`).

## Testing

```bash
uv run pytest tests/crawler/test_extraction.py tests/crawler/test_fetch_outcomes.py tests/crawler/test_browser_fallback.py tests/crawler/test_discovery.py tests/test_wordpress_search_read_post.py -q
uv run ruff check src/web_pages && uv run mypy src/web_pages
```
