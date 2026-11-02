"""Threads (docs/LLD-meta-social-networks.md).

Its own Meta product: the Threads app id and secret (`SOCIAL_THREADS_CLIENT_ID` / `_CLIENT_SECRET`), its own hosts
and version (`graph.threads.com`, `v1.0`). One sign-in is one profile. The long-lived token lasts 60 days and is
renewed while the account posts (`fresh_credentials`). Posts are containers: created, processed (Threads fetches
each image from a public URL), then published.
"""

from __future__ import annotations

import logging
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from src.config import settings
from src.config.settings import SocialAppCredentials
from src.connectors.social.networks.base import (
    ConnectedProfile,
    ConnectError,
    NetworkLimits,
    PreparedImage,
    PreparedPost,
    PublishedPost,
    PublishError,
    PublishErrorKind,
    RecentPost,
    RefreshedCredentials,
)
from src.connectors.social.networks.meta import (
    bearer,
    graph_call,
    graph_json,
    graph_message,
    permalink,
    wait_for_container,
)

log = logging.getLogger(__name__)

NAME = "Threads"
AUTHORIZE_URL = "https://threads.com/oauth/authorize"
GRAPH = "https://graph.threads.com"
API = f"{GRAPH}/v1.0"
TIMEOUT_SECONDS = 30
#: Meta renews a token only once it is a day old; renewing with a month left leaves weeks to retry a failure
RENEW_AFTER = timedelta(hours=24)
RENEW_WITHIN = timedelta(days=30)
TOKEN_LIFETIME = timedelta(days=60)
#: Threads' `media_type`, as the media kinds `recent_posts` reports
MEDIA_KINDS = {"TEXT_POST": "text", "IMAGE": "image", "CAROUSEL_ALBUM": "carousel", "VIDEO": "video"}
#: Joiners and selectors inside an emoji sequence, which Threads counts as their bytes too
EMOJI_PARTS = {"‍", "️", "⃣"}


def threads_length(text: str) -> int:
    """How Threads counts text against its 500: an emoji as its UTF-8 bytes, everything else as 1. Symbols outside
    the Basic Multilingual Plane, `So` symbols and emoji joiners count their bytes, which never under-counts an emoji
    and doesn't penalise accented letters."""
    return sum(
        len(char.encode()) if ord(char) > 0xFFFF or char in EMOJI_PARTS or unicodedata.category(char) == "So" else 1
        for char in text
    )


class ThreadsNetwork:
    key = "threads"
    display_name = "Threads"
    description = "Post as your Threads profile."
    icon = "threads"
    shares_grant = False
    app = "threads"
    scopes = "threads_basic,threads_content_publish"
    limits = NetworkLimits(max_text=500, max_images=20, max_image_side=1440, max_image_bytes=8 * 1024 * 1024,
                           text_length=threads_length, public_media=True)
    reads_posts = True

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        #: Tests answer the Threads API through this
        self._transport = transport

    def configured(self) -> bool:
        return settings.social_app(self.app) is not None

    def authorize_url(self, state: str, code_challenge: str) -> str:
        # Threads documents no PKCE; the sealed state is the CSRF guard
        params = {
            "client_id": self._app().client_id,
            "redirect_uri": settings.social_oauth_redirect_uri,
            "scope": self.scopes,
            "response_type": "code",
            "state": state,
        }
        return f"{AUTHORIZE_URL}?{urlencode(params, quote_via=quote)}"

    async def complete(self, code: str, code_verifier: str) -> list[ConnectedProfile]:
        app = self._app()
        async with self._client() as client:
            short = await self._token(client, "sign-in", "POST", f"{GRAPH}/oauth/access_token", data={
                "client_id": app.client_id, "client_secret": app.client_secret, "code": code,
                "grant_type": "authorization_code", "redirect_uri": settings.social_oauth_redirect_uri,
            })
            # Meta takes the token to exchange only as a query parameter here, next to the app secret
            long = await self._token(client, "long-lived token", "GET", f"{GRAPH}/access_token", params={
                "grant_type": "th_exchange_token", "client_secret": app.client_secret,
                "access_token": str(short["access_token"]),
            })
            response = await client.get(f"{API}/me", headers=bearer(str(long["access_token"])),
                                        params={"fields": "id,username,name,threads_profile_picture_url"})
            if response.status_code != 200:
                raise ConnectError(f"Threads did not return the profile ({graph_message(response)})")
            me = graph_json(response)
        username = str(me.get("username") or me["id"])
        return [ConnectedProfile(
            external_id=str(me["id"]),
            handle=f"@{username}",
            display_name=str(me.get("name") or username),
            avatar_url=me.get("threads_profile_picture_url"),
            credentials=_credentials(long, str(me["id"])),
            scopes=self.scopes,
            expires_at=_expiry(long),
            grant_id=str(me["id"]),
        )]

    async def fresh_credentials(self, credentials: dict[str, Any]) -> RefreshedCredentials | None:
        """A renewed token once the current one is a day old and has under 30 days left. A renewal Threads refuses
        is AUTH; any other failure leaves the current token, which still works, to be renewed next time."""
        now = datetime.now(timezone.utc)
        issued, expires = datetime.fromisoformat(credentials["issued_at"]), datetime.fromisoformat(credentials["expires_at"])
        if now - issued < RENEW_AFTER or expires - now > RENEW_WITHIN or expires <= now:
            return None
        try:
            async with self._client() as client:
                renewed = await graph_call(client, "GET", f"{GRAPH}/refresh_access_token", network=NAME, created=False,
                                           params={"grant_type": "th_refresh_token",
                                                   "access_token": credentials["access_token"]})
        except PublishError as error:
            if error.kind == PublishErrorKind.AUTH:
                raise
            log.warning("Threads token renewal failed, keeping the current token: %s", error)
            return None
        return RefreshedCredentials(_credentials(renewed, credentials["user_id"]), _expiry(renewed))

    async def revoke(self, credentials: dict[str, Any]) -> None:
        try:
            async with self._client() as client:
                response = await client.delete(f"{API}/me/permissions", headers=bearer(credentials["access_token"]))
            if response.status_code != 200:
                log.info("Threads did not end the grant (%s); the person can remove the app in Threads",
                         graph_message(response))
        except Exception as error:  # a failed revoke must not stop the account from being disconnected
            log.warning("Threads grant revoke failed: %s", type(error).__name__)

    async def publish(self, credentials: dict[str, Any], post: PreparedPost) -> PublishedPost:
        user, headers = credentials["user_id"], bearer(credentials["access_token"])
        async with self._client() as client:
            async def container(fields: dict[str, str]) -> str:
                body = await graph_call(client, "POST", f"{API}/{user}/threads", network=NAME, created=False,
                                        headers=headers, data=fields)
                await wait_for_container(client, f"{API}/{body['id']}", network=NAME, headers=headers,
                                         status_field="status", detail_field="error_message")
                return str(body["id"])

            if not post.images:
                creation = await container({"media_type": "TEXT", "text": post.text})
            elif len(post.images) == 1:
                creation = await container({**_image(post.images[0]), "text": post.text})
            else:
                children = [await container({**_image(image), "is_carousel_item": "true"}) for image in post.images]
                creation = await container({"media_type": "CAROUSEL", "children": ",".join(children), "text": post.text})
            published = await graph_call(client, "POST", f"{API}/{user}/threads_publish", network=NAME, created=True,
                                         headers=headers, data={"creation_id": creation})
            post_id = str(published.get("id") or "")
            return PublishedPost(external_id=post_id, url=await permalink(client, f"{API}/{post_id}", headers))

    async def recent_posts(self, credentials: dict[str, Any], limit: int) -> list[RecentPost]:
        async with self._client() as client:
            body = await graph_call(client, "GET", f"{API}/me/threads", network=NAME, created=False,
                                    headers=bearer(credentials["access_token"]),
                                    params={"fields": "id,text,timestamp,permalink,media_type", "limit": str(limit)})
        return [RecentPost(
            external_id=str(item["id"]),
            posted_at=datetime.strptime(item["timestamp"], "%Y-%m-%dT%H:%M:%S%z"),
            text=str(item.get("text") or ""),
            url=item.get("permalink"),
            media=MEDIA_KINDS.get(str(item.get("media_type") or ""), "other"),
        ) for item in body.get("data", [])]

    async def _token(self, client: httpx.AsyncClient, what: str, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        response = await client.request(method, url, **kwargs)
        body = graph_json(response)
        if response.status_code != 200 or not body.get("access_token"):
            raise ConnectError(f"Threads did not grant the {what} ({graph_message(response)})")
        return body

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=TIMEOUT_SECONDS)

    def _app(self) -> SocialAppCredentials:
        app = settings.social_app(self.app)
        if app is None:
            raise ConnectError("Threads is not set up on this server")
        return app


def _credentials(token: dict[str, Any], user_id: str) -> dict[str, Any]:
    return {"access_token": str(token["access_token"]), "user_id": user_id,
            "issued_at": datetime.now(timezone.utc).isoformat(), "expires_at": _expiry(token).isoformat()}


def _expiry(token: dict[str, Any]) -> datetime:
    lifetime = timedelta(seconds=int(token["expires_in"])) if token.get("expires_in") else TOKEN_LIFETIME
    return datetime.now(timezone.utc) + lifetime


def _image(image: PreparedImage) -> dict[str, str]:
    if not image.url:
        raise PublishError(PublishErrorKind.REJECTED, "Threads needs each image at a public URL")
    return {"media_type": "IMAGE", "image_url": image.url, **({"alt_text": image.alt_text} if image.alt_text else {})}

