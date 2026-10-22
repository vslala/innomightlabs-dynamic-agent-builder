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
from pydantic import ValidationError

from main import app
from src.infra_cli_runner.browser import BrowserRenderer, FetchedResource, RenderError
from src.infra_cli_runner.filesystem import FileSystemOperationError, FileSystemService
from src.infra_cli_runner.studio.inspect import inspect_page
from src.infra_cli_runner.studio.models import InspectRequest, WalkthroughRequest, WalkthroughResponse
from src.infra_cli_runner.studio.walkthrough import walkthrough

WORKSPACE_ID = "b" * 48

HOME = b"""<html><head><title>Demo</title><style>body{margin:0}</style></head><body>
<nav><a href="/pricing">Pricing</a></nav>
<h1>Welcome</h1>
<button id="menu" onclick="document.getElementById('panel').hidden = false">Menu</button>
<div id="panel" hidden><a href="/docs">Docs</a></div>
<button>Start free</button><button>Start free</button>
<button disabled>Locked</button>
<label for="q">Search</label><input id="q" oninput="document.getElementById('echo').textContent = this.value"><p id="echo"></p>
<div style="height:1200px"></div>
<h2>Middle heading</h2>
<div style="height:1300px"></div>
<h2>Footer heading</h2>
<script>
  addEventListener('scroll', () => {
    if (scrollY > 1000 && !document.getElementById('deep')) {
      const deep = document.createElement('div');
      deep.id = 'deep';
      deep.textContent = 'reached the bottom';
      document.body.appendChild(deep);
    }
  });
</script></body></html>"""
PRICING = b"<html><head><title>Pricing</title></head><body><h1>Pricing</h1><a href=\"/\">Home</a></body></html>"


class SiteHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = PRICING if self.path.startswith("/pricing") else HOME
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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


def role(role_name: str, name: str, **extra: object) -> dict:
    return {"role": role_name, "name": name, **extra}


BASE = {"request_id": "r1", "workspace_id": WORKSPACE_ID, "url": "https://example.com"}


class WalkthroughModelTests(unittest.TestCase):
    def build(self, **fields: object) -> WalkthroughRequest:
        return WalkthroughRequest(**{**BASE, "output_path": "clips/a.webm", **fields})  # type: ignore[arg-type]

    def test_what_a_recording_needs(self) -> None:
        self.build()
        self.build(rehearse=True, output_path=None)
        for fields in ({"output_path": None}, {"output_path": "clips/a.mp4"}):
            with self.assertRaises(ValidationError, msg=fields):
                self.build(**fields)

    def test_steps_are_checked(self) -> None:
        bad_steps = [
            {"action": "evaluate", "script": "alert(1)"},
            {"action": "goto", "url": "file:///etc/passwd"},
            {"action": "click", "target": {}},
            {"action": "click", "target": role("button", "x"), "extra": 1},
            {"action": "scroll"},
            {"action": "scroll", "to": role("heading", "x"), "by_pixels": 10},
            {"action": "press", "key": "rm -rf"},
            {"action": "mark", "label": "Has Spaces"},
        ]
        for step in bad_steps:
            with self.assertRaises(ValidationError, msg=step):
                self.build(steps=[step])
        self.build(steps=[{"action": "press", "key": "Control+Enter"}, {"action": "scroll", "by_pixels": -300}])

    def test_the_ready_mark_belongs_to_the_runner(self) -> None:
        with self.assertRaises(ValidationError):
            self.build(steps=[{"action": "mark", "label": "ready"}])

    def test_marks_must_be_unique(self) -> None:
        with self.assertRaises(ValidationError):
            self.build(steps=[{"action": "mark", "label": "a"}, {"action": "mark", "label": "a"}])

    def test_the_recording_length_is_capped(self) -> None:
        with patch.dict(os.environ, {"BROWSER_STUDIO_MAX_RECORD_SECONDS": "30"}):
            self.assertEqual(self.build(max_duration_seconds=500).max_duration_seconds, 30)
            self.assertEqual(self.build().max_duration_seconds, 30, "the default is capped too")


class WalkthroughEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.env = patch.dict(os.environ, {"CLI_RUNNER_SHARED_TOKEN": "secret"})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()

    def post(self, body: dict, token: str | None = "secret") -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post("/v1/browser/walkthroughs", json={**BASE, "rehearse": True, **body}, headers=headers)

    def test_requires_the_bearer_token(self) -> None:
        self.assertEqual(self.post({}, token=None).status_code, 401)
        self.assertEqual(self.post({}, token="wrong").status_code, 401)

    def test_a_malformed_request_is_unprocessable(self) -> None:
        self.assertEqual(self.post({"url": "ftp://x"}).status_code, 422)
        self.assertEqual(self.post({"steps": [{"action": "nope"}]}).status_code, 422)
        self.assertEqual(self.post({"rehearse": False}).status_code, 422)

    def test_failures_are_mapped_to_statuses(self) -> None:
        async def broken(*args: object) -> WalkthroughResponse:
            raise RenderError("couldn't load the page: net::ERR_FAILED")

        async def refused(*args: object) -> WalkthroughResponse:
            raise FileSystemOperationError("sandbox_violation", "Path traversal outside the workspace is blocked")

        with patch("src.infra_cli_runner.router.walkthrough", broken):
            self.assertEqual(self.post({}).status_code, 502)
        with patch("src.infra_cli_runner.router.walkthrough", refused):
            response = self.post({})
            self.assertEqual(response.status_code, 400)
            self.assertIn("sandbox_violation", response.json()["detail"])


@unittest.skipUnless(chromium_installed(), "Chromium is not installed: run `uv run playwright install chromium`")
class WalkthroughTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), SiteHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.workspace_root = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace_root.cleanup)
        self.workspace = Path(self.workspace_root.name) / WORKSPACE_ID
        self.files = FileSystemService(workspace_root=Path(self.workspace_root.name))
        self.renderer = BrowserRenderer(fetch=fetch_from_test_server)
        self.addAsyncCleanup(self.renderer.close)

    async def run_walkthrough(self, steps: list[dict], **fields: object) -> WalkthroughResponse:
        fields = {"rehearse": True, "step_timeout_seconds": 2, **fields}
        request = WalkthroughRequest(**{**BASE, "url": f"{self.base}/", "steps": steps, **fields})  # type: ignore[arg-type]
        return await walkthrough(self.renderer, self.files, request)

    async def test_a_rehearsal_performs_the_steps_in_order_and_records_nothing(self) -> None:
        result = await self.run_walkthrough(
            [
                {"action": "click", "target": role("button", "Menu")},
                {"action": "wait_for", "target": role("link", "Docs")},
                {"action": "type", "target": role("textbox", "Search"), "text": "hello"},
                {"action": "wait_for", "target": {"text": "hello"}},
                {"action": "mark", "label": "typed"},
                {"action": "scroll", "by_pixels": 1500, "duration_ms": 400},
                {"action": "wait_for", "target": {"selector": "#deep"}},
                {"action": "scroll", "to": role("heading", "Welcome")},
                {"action": "screenshot", "path": "shots/top.png"},
                {"action": "click", "target": role("link", "Pricing")},
                {"action": "wait_for", "target": role("heading", "Pricing")},
                {"action": "mark", "label": "pricing"},
            ]
        )

        self.assertEqual(result.status, "success", result.failure)
        self.assertIsNone(result.output)
        self.assertEqual([timing.status for timing in result.steps], ["ok"] * 12)
        self.assertEqual([marker.label for marker in result.markers], ["ready", "typed", "pricing"])
        self.assertTrue(result.final_url.endswith("/pricing"))
        self.assertEqual(result.screenshots, ["shots/top.png"])
        self.assertTrue((self.workspace / "shots/top.png").read_bytes().startswith(b"\x89PNG"))
        starts = [timing.started_at_seconds for timing in result.steps]
        self.assertEqual(starts, sorted(starts))
        click = result.steps[0]
        self.assertIsNotNone(click.box)
        self.assertGreater(click.box.width, 0)
        self.assertFalse((self.workspace / ".runs").exists())

    async def test_a_recording_is_saved_as_a_video_with_markers_and_a_cursor(self) -> None:
        result = await self.run_walkthrough(
            [
                {"action": "mark", "label": "start"},
                {"action": "click", "target": role("button", "Menu"), "move_ms": 400},
                {"action": "wait_for", "target": {"selector": "#__studio_cursor"}},
                {"action": "wait", "ms": 600},
                {"action": "mark", "label": "end"},
            ],
            rehearse=False,
            output_path="clips/menu.webm",
        )

        self.assertEqual(result.status, "success", result.failure)
        self.assertEqual(result.output.path, "clips/menu.webm")
        video = (self.workspace / "clips/menu.webm").read_bytes()
        self.assertEqual(video[:4], b"\x1a\x45\xdf\xa3", "a WebM file starts with the EBML header")
        self.assertEqual(result.output.size_bytes, len(video))
        self.assertEqual((result.output.width, result.output.height), (1280, 720))
        ready, start, end = result.markers
        self.assertEqual(ready.label, "ready")
        self.assertLess(ready.at_seconds, start.at_seconds + 0.01, "the page is ready before the first step runs")
        self.assertGreater(end.at_seconds - start.at_seconds, 0.9, "the click's glide and the wait both take time")
        self.assertLessEqual(end.at_seconds, result.output.duration_seconds)
        self.assertFalse((self.workspace / ".runs").exists(), "nothing is left in the staging area")

    async def test_without_the_cursor_overlay_it_is_not_on_the_page(self) -> None:
        result = await self.run_walkthrough(
            [
                {"action": "click", "target": role("button", "Menu")},
                {"action": "wait_for", "target": {"selector": "#__studio_cursor"}, "timeout_ms": 500},
            ],
            rehearse=False,
            output_path="clips/plain.webm",
            show_cursor=False,
        )

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.failure.index, 1)
        self.assertEqual(result.failure.error_code, "timeout")

    async def test_a_missing_target_stops_the_run_and_says_what_the_page_holds(self) -> None:
        result = await self.run_walkthrough(
            [
                {"action": "mark", "label": "before"},
                {"action": "click", "target": role("button", "Start fre")},
                {"action": "mark", "label": "never"},
            ],
            step_timeout_seconds=1,
        )

        self.assertEqual(result.status, "partial")
        self.assertEqual([timing.status for timing in result.steps], ["ok", "failed", "skipped"])
        self.assertEqual([marker.label for marker in result.markers], ["ready", "before"])
        failure = result.failure
        self.assertEqual((failure.index, failure.error_code), (1, "not_found"))
        self.assertIn("Start free", [element.name for element in failure.candidates])
        self.assertIn("Menu", [element.name for element in failure.page.elements])
        self.assertEqual(result.steps[1].error, failure.message)

    async def test_scrolling_to_a_target_reports_where_it_landed_for_a_zoom(self) -> None:
        result = await self.run_walkthrough([{"action": "scroll", "to": role("heading", "Middle heading"), "duration_ms": 300}])

        box = result.steps[0].box
        self.assertIsNotNone(box)
        self.assertAlmostEqual(box.y + box.height / 2, 0.5, delta=0.1, msg="the heading is centred in the view")

    async def test_a_target_that_matches_several_elements_is_refused_until_nth_picks_one(self) -> None:
        ambiguous = await self.run_walkthrough([{"action": "click", "target": {"text": "Start free"}}])
        self.assertEqual(ambiguous.failure.error_code, "ambiguous_target")
        self.assertIn("2 elements", ambiguous.failure.message)

        picked = await self.run_walkthrough([{"action": "click", "target": {"text": "Start free", "nth": 1}}])
        self.assertEqual(picked.status, "success", picked.failure)

    async def test_an_element_that_cannot_be_acted_on_is_not_actionable(self) -> None:
        result = await self.run_walkthrough(
            [{"action": "click", "target": role("button", "Locked")}], step_timeout_seconds=1
        )

        self.assertEqual(result.failure.error_code, "not_actionable")

    async def test_a_page_that_cannot_be_reached_is_a_navigation_failure(self) -> None:
        result = await self.run_walkthrough([{"action": "goto", "url": "http://127.0.0.1:1/"}], step_timeout_seconds=2)

        self.assertEqual(result.failure.error_code, "navigation_failed")

    async def test_running_out_of_time_keeps_the_video_so_far(self) -> None:
        with patch.dict(os.environ, {"BROWSER_STUDIO_MAX_RECORD_SECONDS": "2"}):
            result = await self.run_walkthrough(
                [{"action": "wait", "ms": 8000}, {"action": "mark", "label": "never"}],
                rehearse=False,
                output_path="clips/short.webm",
            )

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.failure.error_code, "timeout")
        self.assertEqual([timing.status for timing in result.steps], ["failed", "skipped"])
        self.assertLess(result.output.duration_seconds, 6)
        self.assertTrue((self.workspace / "clips/short.webm").exists())

    async def test_bad_paths_fail_before_the_browser_starts(self) -> None:
        for steps, fields in (
            ([{"action": "screenshot", "path": "../x.png"}], {}),
            ([{"action": "screenshot", "path": "notes.txt"}], {}),
            ([], {"rehearse": False, "output_path": "../escape.webm"}),
        ):
            with self.assertRaises(FileSystemOperationError, msg=(steps, fields)):
                await self.run_walkthrough(steps, **fields)
        self.assertFalse((self.workspace / ".runs").exists())

    async def test_the_browser_still_cannot_reach_internal_addresses(self) -> None:
        renderer = BrowserRenderer()
        self.addAsyncCleanup(renderer.close)
        request = WalkthroughRequest(**{**BASE, "url": f"{self.base}/", "rehearse": True})  # type: ignore[arg-type]

        with self.assertRaises(RenderError):
            await walkthrough(renderer, self.files, request)

    async def test_inspect_page_can_reach_a_state_first(self) -> None:
        async def inspect(steps: list[dict]):
            request = InspectRequest(request_id="r1", workspace_id=WORKSPACE_ID, url=f"{self.base}/", steps=steps, timeout_seconds=6)  # type: ignore[arg-type]
            return await inspect_page(self.renderer, self.files, request)

        closed = await inspect([])
        opened = await inspect([{"action": "click", "target": role("button", "Menu")}])
        failed = await inspect([{"action": "click", "target": role("button", "Nope")}, {"action": "mark", "label": "x"}])

        self.assertNotIn("Docs", [element.name for element in closed.elements])
        self.assertIn("Docs", [element.name for element in opened.elements])
        self.assertEqual([timing.status for timing in opened.steps], ["ok"])
        self.assertEqual([timing.status for timing in failed.steps], ["failed", "skipped"])
        self.assertIn("Menu", [element.name for element in failed.elements], "the page is still described")


if __name__ == "__main__":
    unittest.main()
