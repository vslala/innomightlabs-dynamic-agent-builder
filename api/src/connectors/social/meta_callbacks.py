"""Meta's deauthorize and data-deletion callbacks (docs/LLD-meta-social-networks.md §9).

Meta calls them when a person removes the app or asks for their data to be deleted, with a `signed_request` signed
by the app's secret. It names only the person (their app-scoped user id), so the accounts are found through their
grant items, in whichever InnomightLabs accounts they were connected. The routes are public and never call Meta back.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from src.config import settings
from src.connectors.social.networks import networks_of_app
from src.connectors.social.networks.base import SocialNetwork
from src.connectors.social.repository import SocialAccountRepository
from src.db import get_dynamodb_resource

log = logging.getLogger(__name__)

PREFIX = "/connectors/social/meta"
#: How long the deletion status page Meta links the person to keeps answering
DELETION_RECORD_TTL_SECONDS = 90 * 24 * 3600

router = APIRouter(prefix=PREFIX, tags=["social-connectors"])


def parse_signed_request(signed_request: str, app_secret: str) -> dict[str, Any]:
    """Meta's format: base64url(signature).base64url(JSON payload), HMAC-SHA256 with the app secret.
    Raises ValueError for a bad signature, another algorithm, or a payload without a user."""
    try:
        encoded_signature, payload = signed_request.split(".", 1)
        signature = _b64url(encoded_signature)
        data = json.loads(_b64url(payload))
    except (ValueError, TypeError) as error:
        raise ValueError("malformed signed_request") from error
    expected = hmac.new(app_secret.encode(), payload.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("bad signature")
    if not isinstance(data, dict) or str(data.get("algorithm", "")).upper() != "HMAC-SHA256" or not data.get("user_id"):
        raise ValueError("unexpected payload")
    return data


@router.post("/{app}/deauthorize")
async def deauthorize(app: str, request: Request) -> dict[str, str]:
    """The person removed the app: posting stops and the Social tab offers Reconnect. Deleting is a separate request."""
    networks, user_id = await _verified(app, request)
    repository = SocialAccountRepository()
    for network in networks:
        for account in repository.for_grant(network.key, user_id):
            repository.mark_needs_reconnect(account, f"Access was removed in {network.display_name}")
    return {}


@router.post("/{app}/data-deletion")
async def data_deletion(app: str, request: Request) -> dict[str, str]:
    """Delete every account the person's grant connected, and answer with Meta's status link and confirmation code."""
    networks, user_id = await _verified(app, request)
    repository = SocialAccountRepository()
    deleted = 0
    for network in networks:
        for account in repository.for_grant(network.key, user_id):
            repository.delete(account)
            deleted += 1
    code = secrets.token_hex(8)
    _table().put_item(Item={
        "pk": f"SocialDataDeletion#{code}", "sk": f"SocialDataDeletion#{code}", "entity_type": "SocialDataDeletion",
        "networks": ", ".join(network.display_name for network in networks), "deleted_accounts": deleted,
        "deleted_at": datetime.now(timezone.utc).isoformat(), "ttl": int(time.time()) + DELETION_RECORD_TTL_SECONDS,
    })
    log.info("Meta data deletion for %s removed %d social accounts (%s)", app, deleted, code)
    return {"url": f"{settings.api_base_url}{PREFIX}/deletion/{code}", "confirmation_code": code}


@router.get("/deletion/{code}", response_class=HTMLResponse)
async def deletion_status(code: str) -> HTMLResponse:
    item = _table().get_item(Key={"pk": f"SocialDataDeletion#{code}", "sk": f"SocialDataDeletion#{code}"}).get("Item")
    if not item or int(item.get("ttl", 0)) < time.time():
        return HTMLResponse(_page("Deletion request not found",
                                  "We have no deletion request with that code. Codes are kept for 90 days."), 404)
    when = datetime.fromisoformat(str(item["deleted_at"])).strftime("%d %B %Y, %H:%M UTC")
    count = int(item.get("deleted_accounts", 0))
    return HTMLResponse(_page("Your data has been deleted", (
        f"Confirmation code {code}. On {when} InnoMight Labs deleted the {item.get('networks', '')} "
        f"{'account' if count == 1 else 'accounts'} you had connected ({count}), with the sign-in we stored for "
        "them. Records of posts already published keep only the account name, status and link, and are deleted "
        "within 180 days. Questions: hello@innomightlabs.com."
    )))


async def _verified(app: str, request: Request) -> tuple[list[SocialNetwork], str]:
    """The networks the Meta app serves and the user the signed request names. 404 for an app we don't have."""
    networks = networks_of_app(app)
    credentials = settings.social_app(app)
    if not networks or credentials is None:
        raise HTTPException(status_code=404, detail="Not found")
    form = await request.form()
    try:
        data = parse_signed_request(str(form.get("signed_request") or ""), credentials.client_secret)
    except ValueError as error:
        log.warning("Refused a Meta %s callback: %s", app, error)
        raise HTTPException(status_code=400, detail="Invalid signed_request") from error
    return networks, str(data["user_id"])


def _b64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _table():
    return get_dynamodb_resource().Table(settings.dynamodb_table)


def _page(title: str, body: str) -> str:
    return (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>{html.escape(title)}</title>"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"></head>"
            "<body style=\"font-family: system-ui, sans-serif; max-width: 40rem; margin: 4rem auto; padding: 0 1rem\">"
            f"<h1>{html.escape(title)}</h1><p>{html.escape(body)}</p></body></html>")
