"""Which app a login belongs to, so the OAuth callback can send the user back to the right frontend.

Apps that share this login are registered in AUTH_APP_URLS as {name: frontend base URL}. The chosen
app travels through the provider round trip inside the signed OAuth `state`.
"""
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException

from ..config import settings

DEFAULT_APP = "innomightlabs"
STATE_TTL = timedelta(minutes=10)


def frontend_url_for(app: str) -> str:
    if app == DEFAULT_APP:
        return settings.frontend_url
    return settings.auth_app_urls[app]


def create_state(app: str) -> str:
    if app != DEFAULT_APP and app not in settings.auth_app_urls:
        raise HTTPException(status_code=400, detail="Unknown app")
    payload = {"app": app, "nonce": secrets.token_urlsafe(16), "exp": datetime.now(timezone.utc) + STATE_TTL}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def app_from_state(state: str | None) -> str:
    """The app a callback belongs to; anything unsigned, expired or unregistered is the default app."""
    if not state:
        return DEFAULT_APP
    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.InvalidTokenError:
        return DEFAULT_APP
    app = payload.get("app")
    return app if app in settings.auth_app_urls else DEFAULT_APP
