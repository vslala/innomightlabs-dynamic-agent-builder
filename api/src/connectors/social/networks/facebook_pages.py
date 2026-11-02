"""Facebook Pages, through Facebook Login for Business (docs/LLD-meta-social-networks.md).

One sign-in connects every Page the person can create content on, one account each, like LinkedIn Pages. The user
token is exchanged for a long-lived one, and the Page tokens `/me/accounts` returns for it have no fixed expiry, so
nothing here refreshes. The user token is kept only to end the grant when the last Page is disconnected.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from src.config import settings
from src.connectors.social.networks.base import (
    ConnectedProfile,
    ConnectError,
    NetworkLimits,
    NothingToPostAs,
    PreparedImage,
    PreparedPost,
    PublishedPost,
    RecentPost,
)
from src.connectors.social.networks.meta import graph_call, graph_json, graph_message

log = logging.getLogger(__name__)

NAME = "Facebook"
TIMEOUT_SECONDS = 30
#: The Page tasks that let a person publish as the Page; an Analyst can't
POSTING_TASKS = {"CREATE_CONTENT", "MANAGE"}
POST_URL = "https://www.facebook.com/"
#: A Page's attachment `media_type`, as the media kinds `recent_posts` reports
MEDIA_KINDS = {"photo": "image", "album": "carousel", "video": "video"}


def graph_url(path: str) -> str:
    return f"https://graph.facebook.com/{settings.social_meta_graph_version}{path}"


class FacebookPagesNetwork:
    key = "facebook_page"
    display_name = "Facebook Pages"
    description = "Post as the Facebook Pages you manage. Connecting adds each Page you choose on Facebook."
    icon = "facebook"
    shares_grant = True
    app = "facebook_pages"
    #: Sent only without a Login configuration (SOCIAL_FACEBOOK_LOGIN_CONFIG_ID), whose own permissions apply then
    scopes = "pages_show_list,pages_manage_posts,pages_read_engagement"
    limits = NetworkLimits(max_text=63_206, max_images=10, max_image_bytes=10 * 1024 * 1024)
    reads_posts = True

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        #: Tests answer the Graph API through this
        self._transport = transport

    def configured(self) -> bool:
        return settings.social_app(self.app) is not None

    def authorize_url(self, state: str, code_challenge: str) -> str:
        # Facebook documents no PKCE for this flow; the sealed state is the CSRF guard
        params = {
            "client_id": self._app().client_id,
            "redirect_uri": settings.social_oauth_redirect_uri,
            "state": state,
            "response_type": "code",
        }
        if settings.social_facebook_login_config_id:
            params |= {"config_id": settings.social_facebook_login_config_id, "override_default_response_type": "true"}
        else:
            params["scope"] = self.scopes
        return f"https://www.facebook.com/{settings.social_meta_graph_version}/dialog/oauth?{urlencode(params, quote_via=quote)}"

    async def complete(self, code: str, code_verifier: str) -> list[ConnectedProfile]:
        app = self._app()
        async with self._client() as client:
            short = await self._token(client, "sign-in", client_id=app.client_id, client_secret=app.client_secret,
                                      redirect_uri=settings.social_oauth_redirect_uri, code=code)
            user_token = await self._token(client, "long-lived token", grant_type="fb_exchange_token",
                                           client_id=app.client_id, client_secret=app.client_secret,
                                           fb_exchange_token=short)
            me = await self._read(client, "/me", user_token, fields="id")
            pages = await self._read(client, "/me/accounts", user_token,
                                     fields="id,name,access_token,tasks,picture{url}", limit="100")
            postable = [page for page in pages.get("data", []) if _can_post(page)]
            if not postable:
                raise NothingToPostAs(await self._why_nothing(client, user_token, pages.get("data", [])))
        return [ConnectedProfile(
            external_id=str(page["id"]),
            handle=str(page.get("name") or f"Facebook Page {page['id']}"),
            display_name=str(page.get("name") or f"Facebook Page {page['id']}"),
            avatar_url=((page.get("picture") or {}).get("data") or {}).get("url"),
            credentials={"page_access_token": page["access_token"], "page_id": str(page["id"]),
                         "user_access_token": user_token},
            scopes=self.scopes,
            grant_id=str(me["id"]),
        ) for page in postable]

    async def revoke(self, credentials: dict[str, Any]) -> None:
        try:
            async with self._client() as client:
                response = await client.delete(graph_url("/me/permissions"),
                                               headers=_bearer(credentials["user_access_token"]))
            if response.status_code != 200:
                log.warning("Facebook did not end the grant (%s)", graph_message(response))
        except Exception as error:  # a failed revoke must not stop the account from being disconnected
            log.warning("Facebook grant revoke failed: %s", type(error).__name__)

    async def publish(self, credentials: dict[str, Any], post: PreparedPost) -> PublishedPost:
        page, headers = credentials["page_id"], _bearer(credentials["page_access_token"])
        async with self._client() as client:
            if len(post.images) == 1:
                # One call uploads the photo and posts it
                body = await graph_call(client, "POST", graph_url(f"/{page}/photos"), network=NAME, created=True,
                                        headers=headers, data={"message": post.text}, files=_source(post.images[0]))
                post_id = str(body.get("post_id") or body.get("id") or "")
            else:
                data: dict[str, str] = {"message": post.text}
                for index, image in enumerate(post.images):
                    # Unpublished photos are invisible until the feed post attaches them, so failing here is safe
                    photo = await graph_call(client, "POST", graph_url(f"/{page}/photos"), network=NAME, created=False,
                                             headers=headers, data={"published": "false"}, files=_source(image))
                    data[f"attached_media[{index}]"] = json.dumps({"media_fbid": str(photo["id"])})
                body = await graph_call(client, "POST", graph_url(f"/{page}/feed"), network=NAME, created=True,
                                        headers=headers, data=data)
                post_id = str(body.get("id") or "")
        return PublishedPost(external_id=post_id, url=f"{POST_URL}{post_id}" if post_id else None)

    async def recent_posts(self, credentials: dict[str, Any], limit: int) -> list[RecentPost]:
        async with self._client() as client:
            body = await graph_call(
                client, "GET", graph_url(f"/{credentials['page_id']}/posts"), network=NAME, created=False,
                headers=_bearer(credentials["page_access_token"]),
                params={"fields": "id,message,created_time,permalink_url,attachments{media_type}", "limit": str(limit)},
            )
        return [RecentPost(
            external_id=str(item["id"]),
            posted_at=datetime.strptime(item["created_time"], "%Y-%m-%dT%H:%M:%S%z"),
            text=str(item.get("message") or ""),
            url=item.get("permalink_url"),
            media=_media(item),
        ) for item in body.get("data", [])]

    async def _why_nothing(self, client: httpx.AsyncClient, token: str, pages: list[dict[str, Any]]) -> str:
        """What the sign-in did grant, to tell "no Page chosen" from "the Login configuration lacks a permission".
        Permission names, Page counts and tasks only: never a token."""
        response = await client.get(graph_url("/me/permissions"), headers=_bearer(token))
        granted = sorted(str(item.get("permission")) for item in graph_json(response).get("data", [])
                         if item.get("status") == "granted")
        tasks = sorted({task for page in pages for task in page.get("tasks") or []})
        return (f"That Facebook sign-in granted no Page it can post as (Pages returned: {len(pages)}, their tasks: "
                f"{', '.join(tasks) or 'none'}; permissions granted: {', '.join(granted) or 'unknown'})")

    async def _token(self, client: httpx.AsyncClient, what: str, **params: str) -> str:
        response = await client.get(graph_url("/oauth/access_token"), params=params)
        token = graph_json(response).get("access_token")
        if response.status_code != 200 or not token:
            raise ConnectError(f"Facebook did not grant the {what} ({graph_message(response)})")
        return str(token)

    async def _read(self, client: httpx.AsyncClient, path: str, token: str, **params: str) -> dict[str, Any]:
        response = await client.get(graph_url(path), params=params, headers=_bearer(token))
        if response.status_code != 200:
            raise ConnectError(f"Facebook did not return {path} ({graph_message(response)})")
        return graph_json(response)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=TIMEOUT_SECONDS)

    def _app(self):
        app = settings.social_app(self.app)
        if app is None:
            raise ConnectError("Facebook is not set up on this server")
        return app


def _can_post(page: dict[str, Any]) -> bool:
    """A Page token, and no task list that rules posting out. Facebook may leave `tasks` out (a Page reached
    through a Business portfolio), and then the Page token is what the person was given to post with."""
    tasks = page.get("tasks")
    return bool(page.get("access_token")) and (tasks is None or bool(POSTING_TASKS & set(tasks)))


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _source(image: PreparedImage) -> dict[str, tuple[str, bytes, str]]:
    return {"source": ("image.jpg", image.data, image.mime_type)}


def _media(item: dict[str, Any]) -> str:
    attachments = (item.get("attachments") or {}).get("data") or []
    if not attachments:
        return "text"
    return MEDIA_KINDS.get(str(attachments[0].get("media_type") or ""), "other")
