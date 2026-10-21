"""LinkedIn member profiles. Sign in with LinkedIn (OpenID Connect) plus `w_member_social`, the self-serve products
"Share on LinkedIn" and "Sign In with LinkedIn using OpenID Connect".

A member token lasts 60 days and a non-partner app gets no refresh token: the account shows "needs reconnect" once it
has run out, so posting uses the stored token as it is.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from src.config import settings
from src.connectors.social.networks.base import (
    ConnectedProfile,
    ConnectError,
    NetworkLimits,
    PreparedImage,
    PreparedPost,
    PublishedPost,
    PublishError,
    PublishErrorKind,
)

log = logging.getLogger(__name__)

AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
REVOKE_URL = "https://www.linkedin.com/oauth/v2/revoke"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
SCOPES = "openid profile w_member_social"
#: LinkedIn's member tokens last 60 days; used only when the response doesn't say
DEFAULT_TOKEN_LIFETIME = timedelta(days=60)
POSTS_URL = "https://api.linkedin.com/rest/posts"
IMAGES_URL = "https://api.linkedin.com/rest/images?action=initializeUpload"
ALT_TEXT_MAX = 4000
#: The Posts API is versioned by month; LinkedIn supports each version for about a year
API_VERSION = "202609"
POST_URL = "https://www.linkedin.com/feed/update/"
TIMEOUT_SECONDS = 15
#: In a post's text LinkedIn reads these as markup (mentions, hashtags, templates) and cuts the post short at them
RESERVED = "\\|{}@[]()<>#*_~"


class LinkedInNetwork:
    key = "linkedin"
    display_name = "LinkedIn"
    icon = "linkedin"
    app = "linked_in"
    limits = NetworkLimits(max_text=3000, max_images=20)

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        #: Tests answer LinkedIn's endpoints through this
        self._transport = transport

    def configured(self) -> bool:
        return settings.social_app(self.app) is not None

    def authorize_url(self, state: str, code_challenge: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self._app().client_id,
            "redirect_uri": settings.social_oauth_redirect_uri,
            "state": state,
            "scope": SCOPES,
        }
        return f"{AUTHORIZE_URL}?{urlencode(params, quote_via=quote)}"

    async def complete(self, code: str, code_verifier: str) -> list[ConnectedProfile]:
        app = self._app()
        async with httpx.AsyncClient(transport=self._transport, timeout=TIMEOUT_SECONDS) as client:
            token = await client.post(TOKEN_URL, data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": app.client_id,
                "client_secret": app.client_secret,
                "redirect_uri": settings.social_oauth_redirect_uri,
            })
            tokens = _json(token)
            if token.status_code != 200 or not tokens.get("access_token"):
                raise ConnectError(f"LinkedIn did not accept the sign-in ({tokens.get('error') or token.status_code})")

            profile = await client.get(USERINFO_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"})
            info = _json(profile)
            if profile.status_code != 200 or not info.get("sub"):
                raise ConnectError(f"LinkedIn did not return the member's profile ({profile.status_code})")

        # Whether LinkedIn sends a refresh token decides if we can refresh before posting or the member must sign in
        # again every ~60 days. Log the fact, never the tokens.
        log.info(
            "LinkedIn sign-in granted: refresh_token=%s expires_in=%s refresh_token_expires_in=%s",
            bool(tokens.get("refresh_token")), tokens.get("expires_in"), tokens.get("refresh_token_expires_in"),
        )
        lifetime = timedelta(seconds=int(tokens["expires_in"])) if tokens.get("expires_in") else DEFAULT_TOKEN_LIFETIME
        expires_at = datetime.now(timezone.utc) + lifetime
        name = str(info.get("name") or " ".join(filter(None, [info.get("given_name"), info.get("family_name")])) or "LinkedIn member")
        credentials: dict[str, Any] = {
            "access_token": tokens["access_token"],
            "expires_at": expires_at.isoformat(),
            "person_urn": f"urn:li:person:{info['sub']}",
        }
        if tokens.get("refresh_token"):
            credentials["refresh_token"] = tokens["refresh_token"]
        return [ConnectedProfile(
            external_id=str(info["sub"]),
            handle=name,
            display_name=name,
            avatar_url=info.get("picture"),
            credentials=credentials,
            scopes=str(tokens.get("scope") or SCOPES),
            expires_at=expires_at,
        )]

    async def revoke(self, credentials: dict[str, Any]) -> None:
        app = self._app()
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=TIMEOUT_SECONDS) as client:
                response = await client.post(REVOKE_URL, data={
                    "client_id": app.client_id,
                    "client_secret": app.client_secret,
                    "token": credentials["access_token"],
                })
            if response.status_code != 200:
                log.warning("LinkedIn did not revoke a token (%s)", response.status_code)
        except Exception as error:  # a failed revoke must not stop the account from being disconnected
            log.warning("LinkedIn token revoke failed: %s", type(error).__name__)

    async def publish(self, credentials: dict[str, Any], post: PreparedPost) -> PublishedPost:
        headers = {
            "Authorization": f"Bearer {credentials['access_token']}",
            "LinkedIn-Version": API_VERSION,
            "X-Restli-Protocol-Version": "2.0.0",
        }
        body: dict[str, Any] = {
            "author": credentials["person_urn"],
            "commentary": escape_commentary(post.text),
            "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=TIMEOUT_SECONDS) as client:
                if post.images:
                    uploaded = [await self._upload(client, headers, credentials["person_urn"], image) for image in post.images]
                    body["content"] = _content(uploaded)
                response = await client.post(POSTS_URL, json=body, headers=headers)
        except httpx.ConnectError as error:
            raise PublishError(PublishErrorKind.TRANSIENT, "Could not reach LinkedIn") from error
        except httpx.HTTPError as error:
            raise PublishError(PublishErrorKind.UNCERTAIN, "LinkedIn did not answer, so the post may or may not exist") from error

        if response.status_code == 201:
            post_urn = response.headers.get("x-restli-id", "")
            return PublishedPost(external_id=post_urn, url=f"{POST_URL}{post_urn}" if post_urn else None)
        raise _publish_error(response)

    async def _upload(self, client: httpx.AsyncClient, headers: dict[str, str], owner: str, image: PreparedImage) -> dict[str, str]:
        """Two steps, neither of which makes a visible post: ask for an upload address, then send the bytes to it."""
        init = await client.post(IMAGES_URL, json={"initializeUploadRequest": {"owner": owner}}, headers=headers)
        value = _json(init).get("value") or {}
        if init.status_code != 200 or not value.get("uploadUrl") or not value.get("image"):
            raise _publish_error(init, created=False)
        sent = await client.put(value["uploadUrl"], content=image.data, headers={"Authorization": headers["Authorization"]})
        if sent.status_code not in (200, 201):
            raise _publish_error(sent, created=False)
        return {"id": value["image"], "altText": image.alt_text[:ALT_TEXT_MAX]}

    def _app(self):
        app = settings.social_app(self.app)
        if app is None:
            raise ConnectError("LinkedIn is not set up on this server")
        return app


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def escape_commentary(text: str) -> str:
    return "".join(f"\\{char}" if char in RESERVED else char for char in text)


def _content(images: list[dict[str, str]]) -> dict[str, Any]:
    """One image is a media post; LinkedIn wants at least two for a multi-image post."""
    return {"media": images[0]} if len(images) == 1 else {"multiImage": {"images": images}}


def _publish_error(response: httpx.Response, created: bool = True) -> PublishError:
    """`created` is False before the post call: nothing visible exists yet, so a server error is safe to try again."""
    detail = str(_json(response).get("message") or "")[:200]
    status = response.status_code
    if status == 401:
        return PublishError(PublishErrorKind.AUTH, "LinkedIn no longer accepts this sign-in")
    if status == 429:
        return PublishError(PublishErrorKind.RATE_LIMITED, "LinkedIn is limiting how often this account can post")
    if status >= 500 and not created:
        return PublishError(PublishErrorKind.TRANSIENT, f"LinkedIn failed while uploading an image ({status})")
    if status >= 500:
        return PublishError(PublishErrorKind.UNCERTAIN, f"LinkedIn failed while posting ({status}), so the post may exist")
    return PublishError(PublishErrorKind.REJECTED, f"LinkedIn refused the post ({status}){': ' + detail if detail else ''}")
