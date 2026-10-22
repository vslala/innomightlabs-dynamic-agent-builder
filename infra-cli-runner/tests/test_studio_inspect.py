from __future__ import annotations

import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from playwright.async_api import async_playwright

from main import app
from src.infra_cli_runner.browser import BrowserRenderer, FetchedResource, RenderError
from src.infra_cli_runner.filesystem import FileSystemOperationError, FileSystemService
from src.infra_cli_runner.studio.inspect import inspect_page
from src.infra_cli_runner.studio.models import InspectRequest, InspectResponse, Target
from src.infra_cli_runner.studio.targets import locate

WORKSPACE_ID = "a" * 48

FIXTURE = b"""<html><head><title>Fixture shop</title><style>body{margin:0}</style></head><body>
<header><nav><a href="/pricing">Pricing</a> <a href="/docs">Docs</a> <a href="/secret" aria-hidden="true">Secret</a></nav></header>
<main>
  <h1>Ship agents faster</h1>
  <button>Start free</button>
  <h2>Features</h2>
  <button>Start free</button>
  <button data-testid="buy" style="display:none">Buy</button>
  <button data-testid="export"><svg width="12" height="12"></svg></button>
  <label for="email">Email</label><input id="email" type="email">
  <div id="host"></div>
  <div style="height:2500px"></div>
  <h2>Later</h2>
</main>
<script>
  document.getElementById('host').attachShadow({mode: 'open'}).innerHTML = '<button>Shadow action</button>';
  window.addEventListener('scroll', () => {
    if (window.scrollY > 400 && !document.getElementById('lazy')) {
      const section = document.createElement('section');
      section.id = 'lazy';
      section.innerHTML = '<h2>Lazy section</h2><a href="/lazy">Lazy link</a>';
      document.querySelector('main').appendChild(section);
    }
  });
</script></body></html>"""


class FixtureHandler(BaseHTTPRequestHandler):
    requested: list[str] = []

    def do_GET(self) -> None:  # noqa: N802
        FixtureHandler.requested.append(self.path)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(FIXTURE)))
        self.end_headers()
        self.wfile.write(FIXTURE)

    def log_message(self, *args: object) -> None:
        pass


async def fetch_from_test_server(method: str, url: str, headers: dict[str, str], body: bytes | None) -> FetchedResource:
    """Stands in for the public internet, which the guarded client would never let this test reach on 127.0.0.1."""
    async with httpx.AsyncClient(follow_redirects=False) as client:
        response = await client.request(method, url, headers=headers, content=body)
    kept = {k: v for k, v in response.headers.items() if k.lower() not in {"content-length", "content-encoding"}}
    return FetchedResource(response.status_code, kept, response.content)


def chromium_installed() -> bool:
    import asyncio

    async def probe() -> bool:
        async with async_playwright() as playwright:
            return os.path.exists(playwright.chromium.executable_path)

    return asyncio.run(probe())


class InspectEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.env = patch.dict(os.environ, {"CLI_RUNNER_SHARED_TOKEN": "secret"})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()

    def post(self, body: dict, token: str | None = "secret") -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        payload = {"request_id": "r1", "workspace_id": WORKSPACE_ID, "url": "https://example.com", **body}
        return self.client.post("/v1/browser/inspections", json=payload, headers=headers)

    def test_requires_the_bearer_token(self) -> None:
        self.assertEqual(self.post({}, token=None).status_code, 401)
        self.assertEqual(self.post({}, token="wrong").status_code, 401)

    def test_only_http_addresses_and_known_fields_are_accepted(self) -> None:
        for url in ("file:///etc/passwd", "javascript:alert(1)", "not a url"):
            self.assertEqual(self.post({"url": url}).status_code, 422, url)
        self.assertEqual(self.post({"bogus": 1}).status_code, 422)
        self.assertEqual(self.post({"workspace_id": "../x"}).status_code, 422)
        self.assertEqual(self.post({"max_elements": 0}).status_code, 422)

    def test_failures_are_mapped_to_statuses(self) -> None:
        async def broken(*args: object) -> InspectResponse:
            raise RenderError("couldn't load the page: net::ERR_FAILED")

        async def refused(*args: object) -> InspectResponse:
            raise FileSystemOperationError("sandbox_violation", "Path traversal outside the workspace is blocked")

        with patch("src.infra_cli_runner.router.inspect_page", broken):
            response = self.post({})
            self.assertEqual(response.status_code, 502)
            self.assertIn("couldn't load the page", response.json()["detail"])
        with patch("src.infra_cli_runner.router.inspect_page", refused):
            response = self.post({})
            self.assertEqual(response.status_code, 400)
            self.assertIn("sandbox_violation", response.json()["detail"])


class TargetTests(unittest.TestCase):
    def test_a_target_has_exactly_one_way_to_find_the_element(self) -> None:
        Target(role="button", name="Start free")
        Target(selector="#x", nth=1)
        for bad in ({}, {"role": "button", "text": "x"}, {"selector": "#x", "name": "x"}, {"role": "Button!"}):
            with self.assertRaises(ValueError, msg=bad):
                Target(**bad)


@unittest.skipUnless(chromium_installed(), "Chromium is not installed: run `uv run playwright install chromium`")
class InspectPageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        FixtureHandler.requested = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}/"
        self.workspace_root = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace_root.cleanup)
        self.files = FileSystemService(workspace_root=Path(self.workspace_root.name))
        self.renderer = BrowserRenderer(fetch=fetch_from_test_server)
        self.addAsyncCleanup(self.renderer.close)

    async def inspect(self, **fields: object) -> InspectResponse:
        request = InspectRequest(request_id="r1", workspace_id=WORKSPACE_ID, url=self.url, **fields)  # type: ignore[arg-type]
        return await inspect_page(self.renderer, self.files, request)

    def named(self, result: InspectResponse, name: str) -> list:
        return [element for element in result.elements if element.name == name]

    async def test_reports_what_a_person_can_act_on(self) -> None:
        result = await self.inspect()

        self.assertEqual(result.title, "Fixture shop")
        self.assertEqual(result.final_url, self.url)
        names = {element.name for element in result.elements}
        self.assertTrue({"Pricing", "Docs", "Start free", "Email", "Shadow action"} <= names, names)
        self.assertNotIn("Secret", names, "an aria-hidden link is not something to click")
        self.assertNotIn("Buy", names, "a display:none button is not on the page")
        pricing = self.named(result, "Pricing")[0]
        self.assertEqual((pricing.role, pricing.section, pricing.in_first_viewport), ("link", "navigation", True))
        self.assertEqual(pricing.target, Target(role="link", name="Pricing"))
        self.assertEqual(self.named(result, "Email")[0].role, "textbox")
        self.assertEqual([element.id for element in result.elements], [f"e{n}" for n in range(1, len(result.elements) + 1)])
        self.assertIsNone(result.outline, "the outline is opt-in")
        self.assertIn("Start free", (await self.inspect(include_outline=True)).outline)

    async def test_duplicates_are_told_apart_with_nth(self) -> None:
        result = await self.inspect()

        first, second = self.named(result, "Start free")
        self.assertEqual((first.target.nth, second.target.nth), (0, 1))
        self.assertEqual((first.section, second.section), ("Ship agents faster", "Features"))
        self.assertLess(first.box.y, second.box.y)

    async def test_an_element_without_a_name_gets_the_next_best_target(self) -> None:
        result = await self.inspect()

        export = next(element for element in result.elements if element.target.selector == '[data-testid="export"]')
        self.assertEqual(export.role, "button")

    async def test_every_target_resolves_to_one_element_in_a_fresh_page(self) -> None:
        result = await self.inspect()

        async with self.renderer.studio_page(width=1280, height=720, timeout_seconds=10) as page:
            await page.goto(self.url)
            # What loads on scroll only exists once the page has been scrolled, as it was while inspecting.
            await page.evaluate("window.scrollTo({top: 3000, behavior: 'instant'})")
            await page.wait_for_selector("#lazy")
            for element in [*result.elements, *result.sections]:
                self.assertEqual(await locate(page, element.target).count(), 1, element)
            heading = result.sections[0]
            self.assertEqual(await locate(page, heading.target).inner_text(), heading.heading)

    async def test_sections_give_scroll_targets_in_page_order(self) -> None:
        result = await self.inspect()

        self.assertEqual([section.heading for section in result.sections], ["Ship agents faster", "Features", "Later", "Lazy section"])
        self.assertEqual([section.level for section in result.sections], [1, 2, 2, 2])
        self.assertEqual(result.sections[1].target, Target(role="heading", name="Features"))
        self.assertEqual([section.top for section in result.sections], sorted(section.top for section in result.sections))

    async def test_content_that_loads_on_scroll_is_found_only_when_scrolling_through(self) -> None:
        scrolled = await self.inspect(scroll_through=True)
        unscrolled = await self.inspect(scroll_through=False)

        self.assertEqual(len(self.named(scrolled, "Lazy link")), 1)
        self.assertFalse(self.named(scrolled, "Lazy link")[0].in_first_viewport)
        self.assertEqual(self.named(unscrolled, "Lazy link"), [])

    async def test_filters_and_the_cap(self) -> None:
        links = await self.inspect(roles=["link"])
        self.assertTrue(links.elements)
        self.assertEqual({element.role for element in links.elements}, {"link"})

        by_name = await self.inspect(query="start")
        self.assertEqual([element.name for element in by_name.elements], ["Start free", "Start free"])

        capped = await self.inspect(max_elements=2)
        self.assertEqual(len(capped.elements), 2)
        self.assertTrue(capped.truncated)
        self.assertFalse((await self.inspect(max_elements=200)).truncated)

    async def test_the_screenshot_lands_in_the_workspace_and_annotating_changes_nothing(self) -> None:
        plain = await self.inspect(screenshot_path="shots/home.png")
        annotated = await self.inspect(screenshot_path="shots/marked.png", annotate=True)

        workspace = Path(self.workspace_root.name) / WORKSPACE_ID
        self.assertEqual(plain.screenshot, "shots/home.png")
        self.assertTrue((workspace / "shots/home.png").read_bytes().startswith(b"\x89PNG"))
        self.assertNotEqual((workspace / "shots/home.png").read_bytes(), (workspace / "shots/marked.png").read_bytes())
        self.assertEqual([e.model_dump() for e in plain.elements], [e.model_dump() for e in annotated.elements])

    async def test_the_screenshot_cannot_leave_the_workspace_or_be_something_else(self) -> None:
        for path in ("../escape.png", "/etc/x.png", "notes.txt"):
            with self.assertRaises(FileSystemOperationError, msg=path):
                await self.inspect(screenshot_path=path)

    async def test_the_browser_cannot_reach_internal_addresses(self) -> None:
        renderer = BrowserRenderer()
        self.addAsyncCleanup(renderer.close)
        request = InspectRequest(request_id="r1", workspace_id=WORKSPACE_ID, url=self.url)

        with self.assertRaises(RenderError):
            await inspect_page(renderer, self.files, request)
        self.assertEqual(FixtureHandler.requested, [])


if __name__ == "__main__":
    unittest.main()
