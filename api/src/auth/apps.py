"""Which app a login belongs to, so the OAuth callback can send the user back to the right frontend.

Apps that share this login are registered in AUTH_APP_URLS as {name: frontend base URL}. The chosen
app travels through the provider round trip inside the signed OAuth `state`.

The store apps (iOS and Android) are one more app, NATIVE_APP. They are public clients: they hold no
secret, so a login for them must carry a PKCE challenge (RFC 7636), and the login code returns through
the app's URL scheme (`{NATIVE_APP_SCHEME}://auth`). It is switched off while NATIVE_APP_SCHEME is empty.

The state also carries a nonce that the browser starting the login holds in a cookie. The callback
only completes when the two match, so nobody can finish their own login in someone else's browser
(login CSRF).
"""
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TypeVar

import jwt
from fastapi import HTTPException
from starlette.responses import Response

from ..config import settings

DEFAULT_APP = "innomightlabs"
NATIVE_APP = "mobile"
STATE_TTL = timedelta(minutes=10)
STATE_AUDIENCE = "login_state"
NONCE_COOKIE = "innomight_login_nonce"
NONCE_COOKIE_PATH = "/auth"

R = TypeVar("R", bound=Response)


#: An S256 challenge is the base64url SHA-256 of the verifier, without padding: always 43 characters.
_S256_CHALLENGE = re.compile(r"[A-Za-z0-9_-]{43}")


def native_app_enabled() -> bool:
    return bool(settings.native_app_scheme)


def is_known_app(app: str) -> bool:
    if app == NATIVE_APP:
        return native_app_enabled()
    return app == DEFAULT_APP or app in settings.auth_app_urls


def is_product_app(app: str) -> bool:
    """The InnomightLabs product itself, on the web or in the store apps (not a partner app sharing the login)."""
    return app in (DEFAULT_APP, NATIVE_APP)


def valid_code_challenge(challenge: str) -> bool:
    return _S256_CHALLENGE.fullmatch(challenge) is not None


@dataclass(frozen=True)
class LoginState:
    state: str
    nonce: str


def frontend_url_for(app: str) -> str:
    if app == DEFAULT_APP:
        return settings.frontend_url
    if app == NATIVE_APP and native_app_enabled():
        return f"{settings.native_app_scheme}://auth"
    return settings.auth_app_urls[app].rstrip("/")


@dataclass(frozen=True)
class LoginContext:
    app: str
    invitation: str | None = None
    #: The PKCE challenge a native login started with; its code is only redeemed with the matching verifier.
    code_challenge: str | None = None


def valid_invitation_hash(invitation: str) -> bool:
    return re.fullmatch(r"[0-9a-fA-F]{64}", invitation) is not None


def create_state(app: str, invitation: str | None = None, code_challenge: str | None = None) -> LoginState:
    if not is_known_app(app):
        raise HTTPException(status_code=400, detail="Unknown app")
    if invitation is not None and (app != DEFAULT_APP or not valid_invitation_hash(invitation)):
        raise HTTPException(status_code=400, detail="Invalid invitation context")
    # Only the native app is a public client: it must prove itself with PKCE, and no other app may send one.
    if (app == NATIVE_APP) != (code_challenge is not None) or (code_challenge and not valid_code_challenge(code_challenge)):
        raise HTTPException(status_code=400, detail="Invalid code challenge")
    nonce = secrets.token_urlsafe(16)
    payload = {"aud": STATE_AUDIENCE, "app": app, "nonce": nonce, "exp": datetime.now(timezone.utc) + STATE_TTL}
    if invitation is not None:
        payload["invitation"] = invitation.lower()
    if code_challenge is not None:
        payload["code_challenge"] = code_challenge
    return LoginState(jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), nonce)


def login_context_from_state(state: str | None, nonce: str | None) -> LoginContext | None:
    """Decode context only when signed, unexpired and started in this browser."""
    if not state or not nonce:
        return None
    try:
        payload = jwt.decode(
            state, settings.jwt_secret, algorithms=[settings.jwt_algorithm], audience=STATE_AUDIENCE,
            options={"require": ["exp", "app", "nonce"]},
        )
    except jwt.InvalidTokenError:
        return None
    if not secrets.compare_digest(str(payload.get("nonce") or ""), nonce):
        return None
    app = payload.get("app")
    if not isinstance(app, str) or not is_known_app(app):
        return None
    code_challenge = payload.get("code_challenge")
    if (app == NATIVE_APP) != (code_challenge is not None) or (
        code_challenge is not None and not (isinstance(code_challenge, str) and valid_code_challenge(code_challenge))
    ):
        return None
    invitation = payload.get("invitation")
    if "invitation" in payload and (
        app != DEFAULT_APP or not isinstance(invitation, str) or not valid_invitation_hash(invitation)
    ):
        return None
    return LoginContext(app, invitation.lower() if invitation is not None else None, code_challenge)


def app_from_state(state: str | None, nonce: str | None) -> str | None:
    """Keep the existing app-only API backed by the same context validation."""
    context = login_context_from_state(state, nonce)
    return context.app if context else None


def invitation_from_state(state: str | None, nonce: str | None) -> str | None:
    context = login_context_from_state(state, nonce)
    return context.invitation if context else None


def remember_nonce(response: R, nonce: str) -> R:
    response.set_cookie(
        NONCE_COOKIE,
        nonce,
        max_age=int(STATE_TTL.total_seconds()),
        path=NONCE_COOKIE_PATH,
        httponly=True,
        secure=settings.api_base_url.startswith("https://"),
        samesite="lax",
    )
    return response


def forget_nonce(response: R) -> R:
    response.delete_cookie(NONCE_COOKIE, path=NONCE_COOKIE_PATH)
    return response
