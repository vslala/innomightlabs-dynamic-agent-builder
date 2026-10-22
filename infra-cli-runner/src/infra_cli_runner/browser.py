"""Renders a page in headless Chromium and returns its HTML, for pages that paint their content with JavaScript.

The URL comes from a customer, so Chromium is never allowed to open a socket itself: it would resolve names on its own,
where a DNS answer could change after we checked it. Every request the page makes is intercepted and sent through the
public-internet-only client in `outbound.py`, and the response is handed back to the page. A redirect is handed back as
a redirect, so each hop is checked the same way. Images, fonts and media are never fetched: the crawler wants text.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import httpx
from playwright.async_api import Browser, BrowserContext, Error as PlaywrightError, Page, Playwright, Route, TimeoutError as PlaywrightTimeout
from playwright.async_api import WebSocketRoute, async_playwright

from src.infra_cli_runner import outbound

MAX_RESOURCE_BYTES = 10 * 1024 * 1024
#: What a page's own requests may carry. Cookies and credentials are never forwarded.
FORWARDED_REQUEST_HEADERS = {"accept", "accept-language", "content-type", "origin", "referer", "user-agent"}
#: Headers that describe how the body was sent; the body is handed to the page decoded.
DROPPED_RESPONSE_HEADERS = {
    "connection", "content-encoding", "content-length", "keep-alive", "set-cookie", "transfer-encoding",
}
#: Chromium inside a container has no user namespaces to build its sandbox from. Pages can't reach the network except
#: through `outbound`, and the container holds no secrets beyond the runner's own token.
LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]


@dataclass(frozen=True)
class ResourcePolicy:
    """Which kinds of page request are never fetched. The network guard itself is the same under every policy."""

    blocked_types: frozenset[str]
    #: Answers requests to `SCENE_ORIGIN` from the workspace (a path in, a resource or None out). A page that isn't a
    #: scene has no such origin, and a request to it goes out like any other and fails: `.invalid` never resolves.
    scene_files: Callable[[str], FetchedResource | None] | None = None


#: Where a scene's own files appear to live. `.invalid` is reserved and can never resolve to a real host.
SCENE_ORIGIN = "https://scene.studio.invalid"
#: The crawler wants text, so images, fonts and media are never fetched.
RENDER_POLICY = ResourcePolicy(frozenset({"image", "media", "font"}))
#: A page looked at or recorded for a person needs to look the way it does for them.
STUDIO_POLICY = ResourcePolicy(frozenset())


class RenderError(Exception):
    """The page couldn't be rendered; the message says why, for the caller's log."""


@dataclass(frozen=True)
class FetchedResource:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class RenderedPage:
    final_url: str
    status: int
    html: str


Fetch = Callable[[str, str, dict[str, str], bytes | None], Awaitable[FetchedResource]]


class PublicFetcher:
    """Fetches what the page asks for from the public internet. Redirects are returned, not followed."""

    def __init__(self) -> None:
        self._client = outbound.async_client(follow_redirects=False, timeout=15.0)

    async def __call__(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> FetchedResource:
        async with self._client.stream(method, url, headers=headers, content=body) as response:
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_RESOURCE_BYTES:
                    raise httpx.TransportError(f"{url} is larger than {MAX_RESOURCE_BYTES} bytes")
                chunks.append(chunk)
            kept = {k: v for k, v in response.headers.items() if k.lower() not in DROPPED_RESPONSE_HEADERS}
            return FetchedResource(response.status_code, kept, b"".join(chunks))

    async def close(self) -> None:
        await self._client.aclose()


class BrowserRenderer:
    def __init__(self, *, fetch: Fetch | None = None, concurrency: int | None = None) -> None:
        self._public_fetcher = None if fetch else PublicFetcher()
        self._fetch: Fetch = fetch or self._public_fetcher  # type: ignore[assignment]
        self._slots = asyncio.Semaphore(concurrency or int(os.getenv("BROWSER_RENDER_CONCURRENCY", "1")))
        # Studio work (inspecting, recording) takes minutes, so it must not hold up the crawler's single slot.
        self._studio_slots = asyncio.Semaphore(int(os.getenv("BROWSER_STUDIO_CONCURRENCY", "1")))
        self._launch_lock = asyncio.Lock()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def render(self, url: str, *, timeout_seconds: float, user_agent: str | None = None) -> RenderedPage:
        """The page's HTML once its scripts have run, or whatever it had painted when time ran out."""
        async with self._slots:
            try:
                async with asyncio.timeout(timeout_seconds + 5):
                    return await self._render(url, timeout_seconds, user_agent)
            except TimeoutError as exc:
                raise RenderError("the browser took too long") from exc

    async def _render(self, url: str, timeout_seconds: float, user_agent: str | None) -> RenderedPage:
        browser = await self._launched()
        context = await browser.new_context(user_agent=user_agent, service_workers="block")
        try:
            await self._guard(context, RENDER_POLICY)
            page = await context.new_page()
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
            except PlaywrightError as exc:
                raise RenderError(f"couldn't load the page: {str(exc).splitlines()[0]}") from exc
            # A page that keeps polling never goes idle; what has painted by the deadline is still worth reading.
            with suppress(PlaywrightTimeout):
                await page.wait_for_load_state("networkidle", timeout=timeout_seconds * 1000 / 2)
            return RenderedPage(final_url=page.url, status=response.status if response else 0, html=await page.content())
        finally:
            await context.close()

    @asynccontextmanager
    async def studio_page(
        self,
        *,
        width: int,
        height: int,
        timeout_seconds: float,
        record_video_dir: Path | None = None,
        scene_files: Callable[[str], FetchedResource | None] | None = None,
    ) -> AsyncIterator[Page]:
        """A fresh page at the given size in its own context, behind the same network guard as `render`.

        With `record_video_dir` the page is recorded at its own size; the video is complete once this context manager
        exits (the browser flushes it when the context closes), and `page.video.path()` says where it is."""
        async with self._studio_slots:
            browser = await self._launched()
            recording = {"record_video_dir": str(record_video_dir), "record_video_size": {"width": width, "height": height}} if record_video_dir else {}
            context = await browser.new_context(
                viewport={"width": width, "height": height}, service_workers="block", **recording
            )
            try:
                await self._guard(context, replace(STUDIO_POLICY, scene_files=scene_files))
                page = await context.new_page()
                page.set_default_timeout(timeout_seconds * 1000)
                yield page
            finally:
                await context.close()

    async def _guard(self, context: BrowserContext, policy: ResourcePolicy) -> None:
        async def serve(route: Route) -> None:
            await self._serve(route, policy)

        await context.route("**/*", serve)
        await context.route_web_socket("**/*", _refuse_web_socket)

    async def _serve(self, route: Route, policy: ResourcePolicy) -> None:
        request = route.request
        if policy.scene_files is not None and request.url.startswith(SCENE_ORIGIN + "/"):
            resource = policy.scene_files(urlparse(request.url).path.lstrip("/"))
            if resource is None:
                await route.fulfill(status=404, body=b"")
            else:
                await route.fulfill(status=resource.status, headers=resource.headers, body=resource.body)
            return
        if request.resource_type in policy.blocked_types or urlparse(request.url).scheme not in ("http", "https"):
            await route.abort()
            return
        headers = {name: value for name, value in request.headers.items() if name.lower() in FORWARDED_REQUEST_HEADERS}
        try:
            resource = await self._fetch(request.method, request.url, headers, request.post_data_buffer)
        except httpx.HTTPError:
            await route.abort()
            return
        await route.fulfill(status=resource.status, headers=resource.headers, body=resource.body)

    async def _launched(self) -> Browser:
        async with self._launch_lock:
            if self._browser is None or not self._browser.is_connected():
                if self._playwright is None:
                    self._playwright = await async_playwright().start()
                try:
                    self._browser = await self._playwright.chromium.launch(args=LAUNCH_ARGS)
                except PlaywrightError as exc:
                    raise RenderError(f"the browser couldn't start: {str(exc).splitlines()[0]}") from exc
            return self._browser

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        if self._public_fetcher is not None:
            await self._public_fetcher.close()


async def _refuse_web_socket(socket: WebSocketRoute) -> None:
    await socket.close()


@lru_cache
def get_browser_renderer() -> BrowserRenderer:
    return BrowserRenderer()
