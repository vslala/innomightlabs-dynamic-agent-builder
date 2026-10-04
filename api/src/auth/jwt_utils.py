from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast
import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..config import settings
from ..users import User, UserRepository

security = HTTPBearer()

# Every token we sign names its audience, and every decoder names the one it accepts,
# so a token issued for one purpose cannot be replayed as another.
OWNER_AUDIENCE = "owner"
WIDGET_VISITOR_AUDIENCE = "widget_visitor"


def app_audience(app: str) -> str:
    """Tokens handed to the backend of an app that shares this login, such as BidSignal."""
    return f"app:{app}"


def create_access_token(user: User, lifetime: timedelta | None = None, audience: str = OWNER_AUDIENCE) -> str:
    payload = {
        "aud": audience,
        "sub": user.email,
        "name": user.name,
        "picture": user.picture,
        "exp": datetime.now(timezone.utc) + (lifetime or timedelta(hours=settings.jwt_expiration_hours)),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, audiences: list[str] | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=audiences or [OWNER_AUDIENCE],
        )
        return cast(dict[str, Any], payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    return _user_for(decode_access_token(credentials.credentials))


async def get_user_for_any_app(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Also accepts the tokens issued to apps sharing this login. Only /auth/me takes those."""
    audiences = [OWNER_AUDIENCE, *(app_audience(app) for app in settings.auth_app_urls)]
    return _user_for(decode_access_token(credentials.credentials, audiences))


def _user_for(payload: dict[str, Any]) -> User:
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user_repo = UserRepository()
    user = user_repo.get_by_email(email)

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user
