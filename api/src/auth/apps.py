"""Which app a login belongs to, so the OAuth callback can send the user back to the right frontend.

Apps that share this login are registered in AUTH_APP_URLS as {name: frontend base URL}. The chosen
app travels through the provider round trip inside the signed OAuth `state`.

The state also carries a nonce that the browser starting the login holds in a cookie. The callback
only completes when the two match, so nobody can finish their own login in someone else's browser
(login CSRF).
"""
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


def create_state(app: str) -> LoginState:
    if app != DEFAULT_APP and app not in settings.auth_app_urls:
        raise HTTPException(status_code=400, detail="Unknown app")
    nonce = secrets.token_urlsafe(16)
    payload = {"aud": STATE_AUDIENCE, "app": app, "nonce": nonce, "exp": datetime.now(timezone.utc) + STATE_TTL}
    return LoginState(jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), nonce)


def app_from_state(state: str | None, nonce: str | None) -> str | None:
    """The app a callback belongs to, or None unless the state is ours, unexpired and started in this browser."""
    if not state or not nonce:
        return None
    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm], audience=STATE_AUDIENCE)
    except jwt.InvalidTokenError:
        return None
    if not secrets.compare_digest(str(payload.get("nonce") or ""), nonce):
        return None
    app = payload.get("app")
    if app != DEFAULT_APP and app not in settings.auth_app_urls:
        return None
    return str(app)


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
