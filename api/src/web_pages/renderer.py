"""Renders a page in a real browser, for sites that paint their content with JavaScript.

A plain fetch of a React or Angular app returns an empty shell, so `fetch_page` asks the infra CLI runner (a private
sidecar that holds headless Chromium) for the page as it looks after its scripts ran. It is a fallback: it is only
asked for a page that came back with HTML and nothing in it, and only by a caller that passes a renderer.
"""

from dataclasses import dataclass
from typing import Optional

import httpx

from src.config.settings import settings


class BrowserRenderError(Exception):
    """The runner couldn't render the page; the message says why, for the crawl's log."""


@dataclass(frozen=True)
class RenderedPage:
    final_url: str
    status: int
    html: str


class PageRenderer:
    def __init__(self, base_url: str, token: str, timeout_seconds: int, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def render(self, url: str, *, user_agent: str) -> RenderedPage:
        payload = {"url": url, "timeout_seconds": self.timeout_seconds, "user_agent": user_agent}
        try:
            # The runner waits up to timeout_seconds for the page, so this client waits a little longer than that.
            async with httpx.AsyncClient(timeout=self.timeout_seconds + 10, transport=self.transport) as client:
                response = await client.post(
                    f"{self.base_url}/v1/browser/render", json=payload, headers={"Authorization": f"Bearer {self.token}"}
                )
        except httpx.HTTPError as exc:
            raise BrowserRenderError(f"the browser service is unreachable: {exc.__class__.__name__}") from exc
        if response.status_code >= 400:
            raise BrowserRenderError(f"the browser service answered HTTP {response.status_code}: {_detail(response)}")
        try:
            body = response.json()
            return RenderedPage(final_url=body["final_url"], status=int(body["status"]), html=body["html"])
        except (ValueError, KeyError, TypeError) as exc:
            raise BrowserRenderError("the browser service returned an invalid response") from exc


def _detail(response: httpx.Response) -> str:
    try:
        return str(response.json().get("detail", ""))[:200]
    except (ValueError, AttributeError):
        return response.text[:200]


def configured_page_renderer() -> Optional[PageRenderer]:
    """The renderer, or None when the fallback is off or there is no runner to ask."""
    if not (settings.crawler_browser_fallback and settings.cli_runner_base_url and settings.cli_runner_shared_token):
        return None
    return PageRenderer(settings.cli_runner_base_url, settings.cli_runner_shared_token, settings.crawler_browser_timeout_seconds)
