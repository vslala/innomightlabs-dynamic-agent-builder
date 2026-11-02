"""Facebook Pages, through Facebook Login for Business (docs/LLD-meta-social-networks.md).

One sign-in connects every Page the person can create content on, one account each, like LinkedIn Pages. The user
token is exchanged for a long-lived one, and the Page tokens `/me/accounts` returns for it have no fixed expiry, so
nothing here refreshes. The user token is kept only to end the grant when the last Page is disconnected.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx

from src.connectors.social.networks.base import (
    ConnectedProfile,
    NetworkLimits,
    NothingToPostAs,
    PreparedImage,
    PreparedPost,
    PublishedPost,
    RecentPost,
    RefreshedCredentials,
)
from src.connectors.social.networks.facebook_login import FacebookLogin, diagnostic, graph_url, permission_problem
from src.connectors.social.networks.meta import bearer, graph_call

NAME = "Facebook"
#: The Page tasks that let a person publish as the Page; an Analyst can't
POSTING_TASKS = {"CREATE_CONTENT", "MANAGE"}
POST_URL = "https://www.facebook.com/"
#: The permissions connecting needs, as the person would describe what each allows
NEEDED_PERMISSIONS = {"pages_show_list": "see your Pages", "pages_manage_posts": "post to your Pages"}
#: A Page's attachment `media_type`, as the media kinds `recent_posts` reports
MEDIA_KINDS = {"photo": "image", "album": "carousel", "video": "video"}


class FacebookPagesNetwork:
    key = "facebook_page"
    display_name = "Facebook Pages"
    description = "Post as the Facebook Pages you manage. On Facebook's screen, tick each Page to connect; you need a Page role that can create content."
    icon = "facebook"
    shares_grant = True
    app = "facebook_pages"
    #: Sent only without a Login configuration (SOCIAL_FACEBOOK_LOGIN_CONFIG_ID), whose own permissions apply then
    scopes = "pages_show_list,pages_manage_posts,pages_read_engagement"
    limits = NetworkLimits(max_text=63_206, max_images=10, max_image_bytes=10 * 1024 * 1024)
    reads_posts = True

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._login = FacebookLogin(transport)

    def configured(self) -> bool:
        return self._login.configured()

    def authorize_url(self, state: str, code_challenge: str) -> str:
        return self._login.authorize_url(state, self.scopes)

    async def complete(self, code: str, code_verifier: str) -> list[ConnectedProfile]:
        async with self._login.client() as client:
            user_token = await self._login.user_token(client, code)
            me = await self._login.read(client, "/me", user_token, fields="id")
            pages = (await self._login.read(client, "/me/accounts", user_token,
                                            fields="id,name,access_token,tasks,picture{url}", limit="100")).get("data", [])
            postable = [page for page in pages if _can_post(page)]
            if not postable:
                raise await self._nothing_to_post_as(client, user_token, pages)
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

    async def fresh_credentials(self, credentials: dict[str, Any]) -> RefreshedCredentials | None:
        """Page tokens have no fixed expiry."""
        return None

    async def revoke(self, credentials: dict[str, Any]) -> None:
        await self._login.revoke(credentials["user_access_token"], NAME)

    async def publish(self, credentials: dict[str, Any], post: PreparedPost) -> PublishedPost:
        page, headers = credentials["page_id"], bearer(credentials["page_access_token"])
        async with self._login.client() as client:
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
        async with self._login.client() as client:
            body = await graph_call(
                client, "GET", graph_url(f"/{credentials['page_id']}/posts"), network=NAME, created=False,
                headers=bearer(credentials["page_access_token"]),
                params={"fields": "id,message,created_time,permalink_url,attachments{media_type}", "limit": str(limit)},
            )
        return [RecentPost(
            external_id=str(item["id"]),
            posted_at=datetime.strptime(item["created_time"], "%Y-%m-%dT%H:%M:%S%z"),
            text=str(item.get("message") or ""),
            url=item.get("permalink_url"),
            media=_media(item),
        ) for item in body.get("data", [])]

    async def _nothing_to_post_as(self, client: httpx.AsyncClient, token: str,
                                  pages: list[dict[str, Any]]) -> NothingToPostAs:
        """Why the sign-in gave no Page to post as, told to the person in Facebook's terms: a permission switched off,
        no Page chosen, or no role that can post on the Pages chosen."""
        status = await self._login.permissions(client, token)
        message = permission_problem(status, NEEDED_PERMISSIONS, "Page")
        if message is None and not pages:
            message = ("No Page was shared with InnoMight Labs. Connect again, choose \"Edit previous settings\" on "
                       "Facebook if it offers it, and tick the Pages you want to post to.")
        elif message is None:
            names = ", ".join(str(page.get("name") or page.get("id")) for page in pages)
            message = (f"Your role on {names} doesn't allow posting. Ask a Page admin for Facebook access that "
                       "includes creating content, then connect again.")
        return NothingToPostAs(message, diagnostic(status, pages))


def _can_post(page: dict[str, Any]) -> bool:
    """A Page token, and no task list that rules posting out. Facebook may leave `tasks` out (a Page reached
    through a Business portfolio), and then the Page token is what the person was given to post with."""
    tasks = page.get("tasks")
    return bool(page.get("access_token")) and (tasks is None or bool(POSTING_TASKS & set(tasks)))


def _source(image: PreparedImage) -> dict[str, tuple[str, bytes, str]]:
    return {"source": ("image.jpg", image.data, image.mime_type)}


def _media(item: dict[str, Any]) -> str:
    attachments = (item.get("attachments") or {}).get("data") or []
    if not attachments:
        return "text"
    return MEDIA_KINDS.get(str(attachments[0].get("media_type") or ""), "other")
