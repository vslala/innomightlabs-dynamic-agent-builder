"""LinkedIn member profiles. Sign in with LinkedIn (OpenID Connect) plus `w_member_social`, the self-serve products
"Share on LinkedIn" and "Sign In with LinkedIn using OpenID Connect".

A member token lasts 60 days and a non-partner app gets no refresh token: the account shows "needs reconnect" once it
has run out. Posting is not here yet; this strategy only connects and disconnects accounts.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from src.config import settings
from src.connectors.social.networks.base import ConnectedProfile, ConnectError

log = logging.getLogger(__name__)

AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
REVOKE_URL = "https://www.linkedin.com/oauth/v2/revoke"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
SCOPES = "openid profile w_member_social"
#: LinkedIn's member tokens last 60 days; used only when the response doesn't say
DEFAULT_TOKEN_LIFETIME = timedelta(days=60)
TIMEOUT_SECONDS = 15


class LinkedInNetwork:
    key = "linkedin"
    display_name = "LinkedIn"
    icon = "linkedin"
    app = "linked_in"

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
