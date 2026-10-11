"""Which app a login belongs to, so the OAuth callback can send the user back to the right frontend.

Apps that share this login are registered in AUTH_APP_URLS as {name: frontend base URL}. The chosen
app travels through the provider round trip inside the signed OAuth `state`.

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
STATE_TTL = timedelta(minutes=10)
STATE_AUDIENCE = "login_state"
NONCE_COOKIE = "innomight_login_nonce"
NONCE_COOKIE_PATH = "/auth"

R = TypeVar("R", bound=Response)


@dataclass(frozen=True)
class LoginState:
    state: str
    nonce: str


def frontend_url_for(app: str) -> str:
    if app == DEFAULT_APP:
        return settings.frontend_url
    return settings.auth_app_urls[app].rstrip("/")


@dataclass(frozen=True)
class LoginContext:
    app: str
    invitation: str | None = None


def valid_invitation_hash(invitation: str) -> bool:
    return re.fullmatch(r"[0-9a-fA-F]{64}", invitation) is not None


def create_state(app: str, invitation: str | None = None) -> LoginState:
    if app != DEFAULT_APP and app not in settings.auth_app_urls:
        raise HTTPException(status_code=400, detail="Unknown app")
    if invitation is not None and (app != DEFAULT_APP or not valid_invitation_hash(invitation)):
        raise HTTPException(status_code=400, detail="Invalid invitation context")
    nonce = secrets.token_urlsafe(16)
    payload = {"aud": STATE_AUDIENCE, "app": app, "nonce": nonce, "exp": datetime.now(timezone.utc) + STATE_TTL}
    if invitation is not None:
        payload["invitation"] = invitation.lower()
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
    if not isinstance(app, str) or (app != DEFAULT_APP and app not in settings.auth_app_urls):
        return None
    invitation = payload.get("invitation")
    if "invitation" in payload and (
        app != DEFAULT_APP or not isinstance(invitation, str) or not valid_invitation_hash(invitation)
    ):
        return None
    return LoginContext(app, invitation.lower() if invitation is not None else None)


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
