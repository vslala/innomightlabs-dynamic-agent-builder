"""
Authentication middleware for token refresh and validation.

This middleware intercepts all requests and:
1. Validates JWT tokens
2. If token is expired but refresh token exists, gets a new access token
3. Adds new JWT token to response headers if refreshed
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple
import jwt
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from ..config import settings
from ..users import User, UserRepository
from .google_oauth import GoogleOAuth


# Header name for sending refreshed tokens to frontend
REFRESHED_TOKEN_HEADER = "X-Refreshed-Token"

# Paths that don't require authentication
PUBLIC_PATHS = {
    "/",
    "/health",
    "/auth/google",
    "/auth/callback",
    "/docs",
    "/openapi.json",
    "/redoc",
}


def decode_token_without_verification(token: str) -> Optional[dict]:
    """Decode JWT token without verifying expiration (to get user email)."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False}
        )
        return payload
    except jwt.InvalidTokenError:
        return None


def is_token_expired(token: str) -> Tuple[bool, Optional[dict]]:
    """Check if token is expired. Returns (is_expired, payload)."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm]
        )
        return False, payload
    except jwt.ExpiredSignatureError:
        # Token is expired, decode without verification to get payload
        payload = decode_token_without_verification(token)
        return True, payload
    except jwt.InvalidTokenError:
        return True, None


def create_access_token(user: User) -> str:
    """Create a new JWT access token for the user."""
    payload = {
        "sub": user.email,
        "name": user.name,
        "picture": user.picture,
        "exp": datetime.utcnow() + timedelta(hours=settings.jwt_expiration_hours),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that handles JWT token validation and refresh.

    For protected routes:
    - Validates the JWT token
    - If expired, attempts to refresh using Google refresh token
    - Adds new JWT to response header if refreshed
    """

    def __init__(self, app):
        super().__init__(app)
        self.user_repository = UserRepository()
        self.google_oauth = GoogleOAuth()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip auth for public paths
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        # Skip auth for OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Extract token from Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid authorization header"}
            )

        token = auth_header.split(" ")[1]

        # Check if token is expired
        is_expired, payload = is_token_expired(token)

        if payload is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token"}
            )

        email = payload.get("sub")
        if not email:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token payload"}
            )

        new_token = None

        # TODO: Add policy based token refresh here, for now just check token expiration
        if is_expired:
            return JSONResponse(
                status_code=401,
                content={"detail": "Token expired"}
            )
        else:
            request.state.auth_token = token
            request.state.user_email = email

        response = await call_next(request)

        # Add refreshed token to response header if token was refreshed
        if new_token:
            response.headers[REFRESHED_TOKEN_HEADER] = new_token

        return response

    async def _refresh_token(self, email: str) -> Optional[str]:
        """
        Attempt to refresh the access token using stored refresh token.

        Returns new JWT token if successful, None otherwise.
        """
        try:
            # Get user from database
            user = self.user_repository.get_by_email(email)
            if not user or not user.refresh_token:
                return None

            # Use Google refresh token to get new access token
            tokens = await self.google_oauth.refresh_access_token(user.refresh_token)

            # If Google returns a new refresh token, update it
            new_refresh_token = tokens.get("refresh_token")
            if new_refresh_token:
                self.user_repository.update_refresh_token(email, new_refresh_token)

            # Generate new JWT for our app
            new_jwt = create_access_token(user)
            return new_jwt

        except Exception as e:
            # Log the error in production
            print(f"Token refresh failed for {email}: {e}")
            return None
