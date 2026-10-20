from __future__ import annotations

import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from playwright.async_api import async_playwright

from main import app
from src.infra_cli_runner.browser import (
    BrowserRenderer,
    FetchedResource,
    PublicFetcher,
    RenderedPage,
    RenderError,
    get_browser_renderer,
)

#: The page ships an empty root and paints it with a script, the way a React or Angular app does.
SHELL = b"""<html><head><title>App</title><script src="/app.js"></script></head>
<body><div id="root"></div><img src="/logo.png"></body></html>"""
SCRIPT = b"setTimeout(() => { document.getElementById('root').innerHTML = '<main><h1>Painted late</h1></main>'; }, 300);"


class PageHandler(BaseHTTPRequestHandler):
    requested: list[str] = []

    def do_GET(self) -> None:  # noqa: N802
        PageHandler.requested.append(self.path)
        if self.path == "/app.js":
            self.respond(200, "application/javascript", SCRIPT)
        elif self.path == "/moved":
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
        else:
            self.respond(200, "text/html; charset=utf-8", SHELL)

    def respond(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
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


class BrowserRenderEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.env = patch.dict(os.environ, {"CLI_RUNNER_SHARED_TOKEN": "secret"})
        self.env.start()

        class FakeRenderer:
            async def render(self, url: str, *, timeout_seconds: float, user_agent: str | None = None) -> RenderedPage:
                if "broken" in url:
                    raise RenderError("couldn't load the page: net::ERR_FAILED")
                return RenderedPage(final_url=url, status=200, html="<main>hello</main>")

        app.dependency_overrides[get_browser_renderer] = FakeRenderer

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.env.stop()

    def post(self, url: str, token: str | None = "secret") -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post("/v1/browser/render", json={"url": url}, headers=headers)

    def test_requires_the_bearer_token(self) -> None:
        self.assertEqual(self.post("https://example.com", token=None).status_code, 401)
        self.assertEqual(self.post("https://example.com", token="wrong").status_code, 401)

    def test_returns_the_rendered_page(self) -> None:
        response = self.post("https://example.com/app")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"final_url": "https://example.com/app", "status": 200, "html": "<main>hello</main>"})

    def test_a_page_that_cannot_load_is_a_bad_gateway(self) -> None:
        response = self.post("https://example.com/broken")
        self.assertEqual(response.status_code, 502)
        self.assertIn("couldn't load the page", response.json()["detail"])

    def test_only_http_addresses_are_accepted(self) -> None:
        for url in ("file:///etc/passwd", "ftp://example.com/", "javascript:alert(1)", "not a url"):
            self.assertEqual(self.post(url).status_code, 422, url)


class PublicFetcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_refuses_loopback_and_private_destinations(self) -> None:
        fetcher = PublicFetcher()
        self.addAsyncCleanup(fetcher.close)
        for url in ("http://127.0.0.1:9/", "http://localhost:9/", "http://10.0.0.1/", "http://169.254.169.254/latest/"):
            with self.assertRaises(httpx.HTTPError, msg=url):
                await fetcher("GET", url, {}, None)


@unittest.skipUnless(chromium_installed(), "Chromium is not installed: run `uv run playwright install chromium`")
class BrowserRenderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        PageHandler.requested = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), PageHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    async def test_returns_content_the_scripts_paint(self) -> None:
        renderer = BrowserRenderer(fetch=fetch_from_test_server)
        self.addAsyncCleanup(renderer.close)

        page = await renderer.render(f"{self.base}/", timeout_seconds=10)

        self.assertEqual(page.status, 200)
        self.assertIn("Painted late", page.html)

    async def test_images_are_not_fetched(self) -> None:
        renderer = BrowserRenderer(fetch=fetch_from_test_server)
        self.addAsyncCleanup(renderer.close)

        await renderer.render(f"{self.base}/", timeout_seconds=10)

        self.assertNotIn("/logo.png", PageHandler.requested)

    async def test_redirects_are_followed_by_the_page(self) -> None:
        renderer = BrowserRenderer(fetch=fetch_from_test_server)
        self.addAsyncCleanup(renderer.close)

        page = await renderer.render(f"{self.base}/moved", timeout_seconds=10)

        self.assertEqual(page.final_url, f"{self.base}/")
        self.assertIn("Painted late", page.html)

    async def test_the_browser_cannot_reach_internal_addresses(self) -> None:
        renderer = BrowserRenderer()
        self.addAsyncCleanup(renderer.close)

        with self.assertRaises(RenderError):
            await renderer.render(f"{self.base}/", timeout_seconds=10)
        self.assertEqual(PageHandler.requested, [])


if __name__ == "__main__":
    unittest.main()
