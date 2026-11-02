"""What Meta's networks share: the Graph API's error shapes and how a call's failure is classified. Each network keeps
its own hosts, fields and tokens (docs/LLD-meta-social-networks.md)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from src.config import settings
from src.connectors.social.networks.base import PublishError, PublishErrorKind

#: Graph error codes (https://developers.facebook.com/docs/graph-api/guides/error-handling)
TOKEN_ERRORS = {102, 190}
THROTTLE_ERRORS = {4, 17, 32, 613}
#: "Unknown error" and "service temporarily unavailable": Meta's side, like a 5xx
SERVER_ERRORS = {1, 2}
DETAIL_MAX = 200
#: How often a container's status is read while Meta fetches and processes its media
POLL_SECONDS = 3.0


def bearer(token: str) -> dict[str, str]:
    """Tokens go in the header, never in a URL that could be logged."""
    return {"Authorization": f"Bearer {token}"}


def graph_json(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def graph_message(response: httpx.Response) -> str:
    """Meta's own words for a failed call, safe to log or show: Graph errors never echo the token."""
    error = graph_json(response).get("error") or {}
    return str(error.get("error_user_msg") or error.get("message") or response.status_code)[:DETAIL_MAX]


def graph_error(response: httpx.Response, network: str, *, created: bool) -> PublishError:
    """`created` is False before the call that makes the post visible: a server error there is safe to retry."""
    error = graph_json(response).get("error") or {}
    code = int(error.get("code") or 0)
    if response.status_code == 401 or code in TOKEN_ERRORS:
        return PublishError(PublishErrorKind.AUTH, f"{network} no longer accepts this sign-in")
    if response.status_code == 429 or code in THROTTLE_ERRORS:
        return PublishError(PublishErrorKind.RATE_LIMITED, f"{network} is limiting how often this account can post")
    if response.status_code >= 500 or code in SERVER_ERRORS or error.get("is_transient"):
        if created:
            return PublishError(PublishErrorKind.UNCERTAIN, f"{network} failed while posting, so the post may exist")
        return PublishError(PublishErrorKind.TRANSIENT, f"{network} failed before posting ({response.status_code})")
    return PublishError(PublishErrorKind.REJECTED, f"{network} refused the post: {graph_message(response)}")


async def graph_call(client: httpx.AsyncClient, method: str, url: str, *, network: str, created: bool,
                     **kwargs: Any) -> dict[str, Any]:
    """One Graph call, its failure classified. `created` as for `graph_error`: True for the call that posts."""
    try:
        response = await client.request(method, url, **kwargs)
    except httpx.ConnectError as error:
        raise PublishError(PublishErrorKind.TRANSIENT, f"Could not reach {network}") from error
    except httpx.HTTPError as error:
        if created:
            raise PublishError(PublishErrorKind.UNCERTAIN, f"{network} did not answer, so the post may exist") from error
        raise PublishError(PublishErrorKind.TRANSIENT, f"{network} did not answer") from error
    if response.status_code != 200:
        raise graph_error(response, network, created=created)
    return graph_json(response)


async def wait_for_container(client: httpx.AsyncClient, url: str, *, network: str, headers: dict[str, str],
                             status_field: str, detail_field: str) -> None:
    """Wait until a container (Threads, Instagram) is FINISHED, so publishing it can't fail on unprocessed media.

    Nothing is visible yet, so a failure here is safe to retry (TRANSIENT), except a container Meta refused (ERROR,
    usually media it couldn't fetch or read), which is REJECTED with Meta's reason. The wait is bounded by
    `social_publish_timeout_seconds`."""
    deadline = time.monotonic() + settings.social_publish_timeout_seconds
    while True:
        body = await graph_call(client, "GET", url, network=network, created=False, headers=headers,
                                params={"fields": f"{status_field},{detail_field}"})
        status = str(body.get(status_field) or "")
        if status in ("FINISHED", "PUBLISHED"):
            return
        if status == "ERROR":
            detail = str(body.get(detail_field) or "")[:DETAIL_MAX] or "no reason given"
            raise PublishError(PublishErrorKind.REJECTED, f"{network} could not use the post's media: {detail}")
        if status == "EXPIRED":
            raise PublishError(PublishErrorKind.TRANSIENT, f"{network} let the post lapse before it was published")
        if time.monotonic() >= deadline:
            raise PublishError(PublishErrorKind.TRANSIENT, f"{network} was still processing the post's media")
        await asyncio.sleep(POLL_SECONDS)


async def permalink(client: httpx.AsyncClient, url: str, headers: dict[str, str]) -> str | None:
    """A published post's link. The post exists already, so a link that can't be read is None, never a failure."""
    try:
        response = await client.get(url, headers=headers, params={"fields": "permalink"})
    except httpx.HTTPError:
        return None
    return graph_json(response).get("permalink") if response.status_code == 200 else None
