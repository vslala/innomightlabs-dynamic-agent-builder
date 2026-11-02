"""Instagram professional accounts, through the Facebook sign-in (docs/LLD-meta-social-networks.md).

Meta no longer offers Instagram Login to new apps, so Instagram connects through Facebook Login for Business, the
same app and Login configuration as Facebook Pages: every Instagram Business or Creator account linked to a Page the
person shares becomes one account. It posts with that Page's token, which has no fixed expiry, on graph.facebook.com.
Posts are containers: Instagram fetches each image from a public URL, processes it, then the container is published.
"""

from __future__ import annotations

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
    PublishError,
    PublishErrorKind,
    RecentPost,
    RefreshedCredentials,
)
from src.connectors.social.networks.facebook_login import FacebookLogin, diagnostic, graph_url, permission_problem
from src.connectors.social.networks.meta import bearer, graph_call, permalink, wait_for_container

NAME = "Instagram"
#: The permissions connecting and posting need, as the person would describe what each allows
NEEDED_PERMISSIONS = {
    "pages_show_list": "see your Pages",
    "instagram_basic": "see the Instagram accounts linked to them",
    "instagram_content_publish": "post to Instagram",
}
#: Instagram's `media_type`, as the media kinds `recent_posts` reports
MEDIA_KINDS = {"IMAGE": "image", "CAROUSEL_ALBUM": "carousel", "VIDEO": "video"}


class InstagramNetwork:
    key = "instagram"
    display_name = "Instagram"
    description = ("Post as the Instagram professional accounts linked to your Facebook Pages. On Facebook's screen, "
                   "tick the Pages your Instagram accounts are linked to. Every post needs an image.")
    icon = "instagram"
    #: One Facebook sign-in covers Facebook Pages and every Instagram account linked to them
    shares_grant = True
    app = "facebook_pages"
    #: Sent only without a Login configuration (SOCIAL_FACEBOOK_LOGIN_CONFIG_ID), whose own permissions apply then
    scopes = "pages_show_list,pages_read_engagement,instagram_basic,instagram_content_publish"
    #: Meta's carousel page gives 20 items in one place and stricter caps in another; 10 is safe either way
    limits = NetworkLimits(max_text=2200, max_images=10, requires_image=True, max_image_side=1440,
                           max_image_bytes=8 * 1024 * 1024, aspect_range=(4 / 5, 1.91), max_hashtags=30,
                           max_mentions=20, public_media=True)
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
            pages = (await self._login.read(
                client, "/me/accounts", user_token, limit="100",
                fields="id,name,access_token,instagram_business_account{id,username,name,profile_picture_url}",
            )).get("data", [])
            linked = {str(page["instagram_business_account"]["id"]): page for page in pages
                      if page.get("access_token") and (page.get("instagram_business_account") or {}).get("id")}
            if not linked:
                raise await self._nothing_to_post_as(client, user_token, pages)
        profiles = []
        for instagram_id, page in linked.items():
            account = page["instagram_business_account"]
            username = str(account.get("username") or instagram_id)
            profiles.append(ConnectedProfile(
                external_id=instagram_id,
                handle=f"@{username}",
                display_name=str(account.get("name") or username),
                avatar_url=account.get("profile_picture_url"),
                credentials={"page_access_token": page["access_token"], "instagram_id": instagram_id,
                             "page_id": str(page["id"]), "user_access_token": user_token},
                scopes=self.scopes,
                grant_id=str(me["id"]),
            ))
        return profiles

    async def fresh_credentials(self, credentials: dict[str, Any]) -> RefreshedCredentials | None:
        """It posts with a Page token, which has no fixed expiry."""
        return None

    async def revoke(self, credentials: dict[str, Any]) -> None:
        await self._login.revoke(credentials["user_access_token"], NAME)

    async def publish(self, credentials: dict[str, Any], post: PreparedPost) -> PublishedPost:
        instagram, headers = credentials["instagram_id"], bearer(credentials["page_access_token"])
        async with self._login.client() as client:
            async def container(fields: dict[str, str]) -> str:
                body = await graph_call(client, "POST", graph_url(f"/{instagram}/media"), network=NAME, created=False,
                                        headers=headers, data=fields)
                await wait_for_container(client, graph_url(f"/{body['id']}"), network=NAME, headers=headers,
                                         status_field="status_code", detail_field="status")
                return str(body["id"])

            if len(post.images) == 1:
                image = post.images[0]
                creation = await container({**_image(image), "caption": post.text,
                                            **({"alt_text": image.alt_text} if image.alt_text else {})})
            else:
                # The caption goes on the carousel, never on its items
                children = [await container({**_image(image), "is_carousel_item": "true"}) for image in post.images]
                creation = await container({"media_type": "CAROUSEL", "children": ",".join(children),
                                            "caption": post.text})
            published = await graph_call(client, "POST", graph_url(f"/{instagram}/media_publish"), network=NAME,
                                         created=True, headers=headers, data={"creation_id": creation})
            post_id = str(published.get("id") or "")
            return PublishedPost(external_id=post_id, url=await permalink(client, graph_url(f"/{post_id}"), headers))

    async def recent_posts(self, credentials: dict[str, Any], limit: int) -> list[RecentPost]:
        async with self._login.client() as client:
            body = await graph_call(client, "GET", graph_url(f"/{credentials['instagram_id']}/media"), network=NAME,
                                    created=False, headers=bearer(credentials["page_access_token"]),
                                    params={"fields": "id,caption,timestamp,permalink,media_type", "limit": str(limit)})
        return [RecentPost(
            external_id=str(item["id"]),
            posted_at=datetime.strptime(item["timestamp"], "%Y-%m-%dT%H:%M:%S%z"),
            text=str(item.get("caption") or ""),
            url=item.get("permalink"),
            media=MEDIA_KINDS.get(str(item.get("media_type") or ""), "other"),
        ) for item in body.get("data", [])]

    async def _nothing_to_post_as(self, client: httpx.AsyncClient, token: str,
                                  pages: list[dict[str, Any]]) -> NothingToPostAs:
        """Why the sign-in gave no Instagram account: a permission missing, no Page shared, or no professional
        Instagram account linked to the Pages shared."""
        status = await self._login.permissions(client, token)
        message = permission_problem(status, NEEDED_PERMISSIONS, "Instagram account")
        if message is None and not pages:
            message = ("No Page was shared with InnoMight Labs. Connect again, choose \"Edit previous settings\" on "
                       "Facebook if it offers it, and tick the Page your Instagram account is linked to.")
        elif message is None:
            names = ", ".join(str(page.get("name") or page.get("id")) for page in pages)
            message = (f"No Instagram professional account is linked to {names}. In Instagram, switch the account to "
                       "a Business or Creator account and link it to one of these Pages, then connect again.")
        return NothingToPostAs(message, diagnostic(status, pages))


def _image(image: PreparedImage) -> dict[str, str]:
    if not image.url:
        raise PublishError(PublishErrorKind.REJECTED, "Instagram needs each image at a public URL")
    return {"image_url": image.url}
