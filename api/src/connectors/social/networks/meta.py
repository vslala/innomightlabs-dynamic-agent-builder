"""What Meta's networks share: the Graph API's error shapes and how a call's failure is classified. Each network keeps
its own hosts, fields and tokens (docs/LLD-meta-social-networks.md)."""

from __future__ import annotations

from typing import Any

import httpx

from src.connectors.social.networks.base import PublishError, PublishErrorKind

#: Graph error codes (https://developers.facebook.com/docs/graph-api/guides/error-handling)
TOKEN_ERRORS = {102, 190}
THROTTLE_ERRORS = {4, 17, 32, 613}
#: "Unknown error" and "service temporarily unavailable": Meta's side, like a 5xx
SERVER_ERRORS = {1, 2}
DETAIL_MAX = 200


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
