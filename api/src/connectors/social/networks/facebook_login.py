"""The Facebook Login for Business sign-in that Facebook Pages and Instagram share (docs/LLD-meta-social-networks.md).

One Meta app (`facebook_pages`), one Login configuration and one grant per person: Instagram professional accounts
are reached through the Pages they are linked to. Each network asks `/me/accounts` for what it posts as; this holds
the sign-in, the reads and the explanation of a sign-in that granted too little.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from src.config import settings
from src.config.settings import SocialAppCredentials
from src.connectors.social.networks.base import ConnectError
from src.connectors.social.networks.meta import bearer, graph_json, graph_message

log = logging.getLogger(__name__)

APP = "facebook_pages"
TIMEOUT_SECONDS = 30


def graph_url(path: str) -> str:
    return f"https://graph.facebook.com/{settings.social_meta_graph_version}{path}"


class FacebookLogin:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        #: Tests answer the Graph API through this
        self._transport = transport

    def configured(self) -> bool:
        return settings.social_app(APP) is not None

    def authorize_url(self, state: str, scopes: str) -> str:
        """With a Login configuration (SOCIAL_FACEBOOK_LOGIN_CONFIG_ID) its permissions apply, not `scopes`."""
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
            params["scope"] = scopes
        return f"https://www.facebook.com/{settings.social_meta_graph_version}/dialog/oauth?{urlencode(params, quote_via=quote)}"

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=TIMEOUT_SECONDS)

    async def user_token(self, client: httpx.AsyncClient, code: str) -> str:
        """The sign-in's code as a long-lived user token (about 60 days); the Page tokens read with it don't expire."""
        app = self._app()
        short = await self._token(client, "sign-in", client_id=app.client_id, client_secret=app.client_secret,
                                  redirect_uri=settings.social_oauth_redirect_uri, code=code)
        return await self._token(client, "long-lived token", grant_type="fb_exchange_token", client_id=app.client_id,
                                 client_secret=app.client_secret, fb_exchange_token=short)

    async def read(self, client: httpx.AsyncClient, path: str, token: str, **params: str) -> dict[str, Any]:
        response = await client.get(graph_url(path), params=params, headers=bearer(token))
        if response.status_code != 200:
            raise ConnectError(f"Facebook did not return {path} ({graph_message(response)})")
        return graph_json(response)

    async def permissions(self, client: httpx.AsyncClient, token: str) -> dict[str, str] | None:
        """Each permission the sign-in asked for, `granted` or `declined`; None when Facebook won't say."""
        response = await client.get(graph_url("/me/permissions"), headers=bearer(token))
        if response.status_code != 200:
            return None
        return {str(item.get("permission")): str(item.get("status")) for item in graph_json(response).get("data") or []}

    async def revoke(self, user_token: str, network: str) -> None:
        """Ends the person's whole grant: every Page and Instagram account it connected stops working."""
        try:
            async with self.client() as client:
                response = await client.delete(graph_url("/me/permissions"), headers=bearer(user_token))
            if response.status_code != 200:
                log.warning("%s did not end the grant (%s)", network, graph_message(response))
        except Exception as error:  # a failed revoke must not stop the account from being disconnected
            log.warning("%s grant revoke failed: %s", network, type(error).__name__)

    async def _token(self, client: httpx.AsyncClient, what: str, **params: str) -> str:
        response = await client.get(graph_url("/oauth/access_token"), params=params)
        token = graph_json(response).get("access_token")
        if response.status_code != 200 or not token:
            raise ConnectError(f"Facebook did not grant the {what} ({graph_message(response)})")
        return str(token)

    def _app(self) -> SocialAppCredentials:
        app = settings.social_app(APP)
        if app is None:
            raise ConnectError("Facebook is not set up on this server")
        return app


def permission_problem(status: dict[str, str] | None, needed: dict[str, str], what: str) -> str | None:
    """What to tell the person when a permission `needed` (name: what it lets us do) is missing, else None. `what` is
    the thing that couldn't be connected ("Page", "Instagram account").

    A permission Facebook never asked for is our app's setup (the Login configuration), not the person's choice."""
    not_asked = [permission for permission in needed if status is not None and permission not in status]
    if not_asked:
        log.error("The Facebook Login configuration doesn't ask for %s", ", ".join(not_asked))
        return (f"InnoMight Labs' Facebook connection isn't set up to ask to "
                f"{' and '.join(needed[permission] for permission in not_asked)} yet, so no {what} could be "
                "connected. This is on our side: contact hello@innomightlabs.com.")
    declined = [need for permission, need in needed.items() if (status or {}).get(permission) == "declined"]
    if declined:
        return (f"Facebook didn't give permission to {' and '.join(declined)}. Connect again and leave every "
                "permission Facebook asks for switched on.")
    return None


def diagnostic(status: dict[str, str] | None, pages: list[dict[str, Any]]) -> str:
    """For the log only: what the sign-in granted and returned, never a token."""
    tasks = sorted({task for page in pages for task in page.get("tasks") or []})
    granted = sorted(permission for permission, state in (status or {}).items() if state == "granted")
    return (f"(Pages returned: {len(pages)}, their tasks: {', '.join(tasks) or 'none'}; permissions granted: "
            f"{', '.join(granted) or 'unknown'})")
