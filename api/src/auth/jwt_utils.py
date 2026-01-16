from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast
import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..config import settings
from ..users import User, UserRepository

security = HTTPBearer()


def create_access_token(user: User) -> str:
    payload = {
        "sub": user.email,
        "name": user.name,
        "picture": user.picture,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expiration_hours),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        return cast(dict[str, Any], payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    token = credentials.credentials
    payload = decode_access_token(token)

    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user_repo = UserRepository()
    user = user_repo.get_by_email(email)

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user
