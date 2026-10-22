"""Calls the infra CLI runner's browser and media endpoints on behalf of the Browser Studio skill.

The runner validates every request strictly and says which field is wrong, so this skill doesn't repeat its models. What
it does own: the identity fields (the agent can never name another conversation's workspace), how long to wait for each
kind of job, and turning a refusal into a message an agent can act on.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx

from src.config import settings
from src.skills.workspaces import workspace_id_from_context

#: Beyond the runner's own limit for a job: its setup and finishing, and the trip there and back.
GRACE_SECONDS = 45
MAX_DETAIL_LINES = 5
MAX_DETAIL_CHARS = 700


def _number(arguments: dict[str, Any], key: str, default: float) -> float:
    value = arguments.get(key)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else default


@dataclass(frozen=True)
class Endpoint:
    action: str
    path: str
    #: How long the runner may take over these arguments, in seconds.
    wait: Callable[[dict[str, Any]], float]


ENDPOINTS: list[Endpoint] = [
    Endpoint("inspect_page", "/v1/browser/inspections", lambda a: _number(a, "timeout_seconds", 25) + 25),
    Endpoint("record_walkthrough", "/v1/browser/walkthroughs", lambda a: _number(a, "max_duration_seconds", 120) + GRACE_SECONDS),
    # A scene is captured at about four frames a second at worst, plus the browser's start and ffmpeg's finish.
    Endpoint("render_scene", "/v1/browser/scenes", lambda a: _number(a, "duration_seconds", 3) * _number(a, "fps", 30) * 0.25 + GRACE_SECONDS + 15),
    Endpoint("compose_video", "/v1/media/compositions", lambda a: 300 + 15),
    Endpoint("probe_media", "/v1/media/probes", lambda a: 60 + 15),
]


def endpoint_for(action: str) -> Endpoint:
    try:
        return next(endpoint for endpoint in ENDPOINTS if endpoint.action == action)
    except StopIteration:
        raise ValueError(f"Browser Studio has no action {action!r}") from None


class BrowserStudioClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def call(self, action: str, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if not settings.cli_runner_base_url:
            raise RuntimeError("CLI runner is not configured. Set CLI_RUNNER_BASE_URL.")
        if not settings.cli_runner_shared_token:
            raise RuntimeError("CLI runner is not configured. Set CLI_RUNNER_SHARED_TOKEN.")
        endpoint = endpoint_for(action)
        request_id = str(
            context.get("user_message_id") or context.get("automation_run_id") or context.get("conversation_id") or uuid4()
        )
        # The identity fields go last, so nothing in `arguments` can replace them.
        payload = {**arguments, "request_id": request_id[:128], "workspace_id": workspace_id_from_context(context)}
        wait = min(float(settings.browser_studio_timeout_seconds), endpoint.wait(arguments))
        headers = {"Authorization": f"Bearer {settings.cli_runner_shared_token}"}
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(wait, connect=min(5.0, wait)), transport=self._transport
            ) as http:
                response = await http.post(f"{settings.cli_runner_base_url.rstrip('/')}{endpoint.path}", json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"{action} didn't finish within {wait:.0f}s. The browser studio does one job at a time, so it may be busy: "
                "try again, or ask for something shorter."
            ) from exc
        except httpx.ConnectError as exc:
            raise RuntimeError(f"{action} failed: the browser studio runner is unreachable.") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"{action} failed: {exc.__class__.__name__} talking to the browser studio runner.") from exc

        if response.status_code >= 400:
            raise RuntimeError(f"{action} failed: {describe_failure(response)}")
        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError(f"{action} failed: the browser studio runner returned an invalid response.") from exc
        if not isinstance(body, dict):
            raise RuntimeError(f"{action} failed: the browser studio runner returned an invalid response.")
        return body


def describe_failure(response: httpx.Response) -> str:
    """What the runner refused, in words: its own message for a failed page or a bad timeline, and `path: reason` lines
    for a field it rejected."""
    if response.status_code == 404:
        # A route that doesn't exist, not a missing file (the runner reports those as 400): the runner is an older version
        # than this skill, which happens when the API is deployed before it.
        return "the browser studio runner doesn't have this endpoint, so it is running an older version than this skill needs. Rebuild or redeploy the infra CLI runner; retrying won't help."
    if response.status_code in (401, 403):
        return "the browser studio runner rejected this service's credentials (a deployment problem, not something to retry)."
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    if isinstance(detail, str):
        return _bounded(detail)
    if isinstance(detail, list):
        lines = [_field_problem(item) for item in detail[:MAX_DETAIL_LINES] if isinstance(item, dict)]
        more = f" (and {len(detail) - MAX_DETAIL_LINES} more)" if len(detail) > MAX_DETAIL_LINES else ""
        return _bounded("; ".join(lines) + more) if lines else f"HTTP {response.status_code}"
    return f"HTTP {response.status_code} {_bounded(response.text, 300)}"


def _field_problem(item: dict[str, Any]) -> str:
    location = ".".join(str(part) for part in item.get("loc", []) if part != "body")
    message = str(item.get("msg", "invalid")).removeprefix("Value error, ")
    return f"{location}: {message}" if location else message


def _bounded(value: str, limit: int = MAX_DETAIL_CHARS) -> str:
    return value if len(value) <= limit else value[:limit] + "...[truncated]"


def get_browser_studio_client() -> BrowserStudioClient:
    return BrowserStudioClient()
