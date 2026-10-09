"""
Authentication middleware for owner routes.

Accepts only owner tokens (aud=owner) for users that exist and are active.
"""

from typing import Any, Optional, Tuple, cast
import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from ..config import settings
from ..users import UserRepository
from ..users.models import UserStatus
from ..agents.repository import AgentRepository
from .jwt_utils import OWNER_AUDIENCE, app_audience


# Paths that don't require authentication
PUBLIC_PATHS = {
    "/",
    "/health",
    "/auth/google",
    "/auth/callback",
    "/auth/callback/google",
    "/auth/callback/cognito",
    "/auth/google-drive/callback",
    "/auth/google-mail/callback",
    "/auth/google-ads/callback",
    "/skills/agent2agent_client/oauth/callback",
    "/connectors/mcp/oauth/callback",
    "/auth/cognito",
    "/auth/token",
    "/auth/session",
    "/auth/refresh",
    "/auth/revoke",
    "/auth/local/signup",
    "/auth/local/login",
    "/docs",
    "/test-logging",
    "/openapi.json",
    "/redoc",
    "/payments/stripe/webhook",
    "/payments/stripe/pricing",
    "/blueprints/schema/v2.json",
    "/blueprints/reference",
    "/contact/submit",
    "/contact/enquiry",
    "/.well-known/agent-card.json",
}

# Path prefixes that use different authentication (not JWT)
WIDGET_PATH_PREFIX = "/widget"
ANALYTICS_AGENT_PATH_PREFIX = "/analytics/agents/"
DOWNLOADS_PLUGINS_PATH_PREFIX = "/downloads/plugins"
A2A_PATH_PREFIX = "/a2a/"
A2A_WELL_KNOWN_PATH_PREFIX = "/.well-known/agents/"
PUBLIC_API_PATH_PREFIX = "/v1/"
EMBED_PATH_PREFIX = "/embed/"


def token_audiences_for(path: str) -> list[str]:
    """Owner routes take only owner tokens. /auth/me is the one route apps sharing this login call with a user token."""
    if path == "/auth/me":
        return [OWNER_AUDIENCE, *(app_audience(app) for app in settings.auth_app_urls)]
    return [OWNER_AUDIENCE]


def decode_token(token: str, audiences: list[str]) -> Tuple[bool, Optional[dict[str, Any]]]:
    """(is_expired, payload); the payload is None for a token that is not ours or not for this audience."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm], audience=audiences)
        return False, cast(dict[str, Any], payload)
    except jwt.ExpiredSignatureError:
        return True, {}
    except jwt.InvalidTokenError:
        return True, None


class AuthMiddleware(BaseHTTPMiddleware):
    """Validates the owner JWT on every route that is not public or authenticated another way."""

    def __init__(self, app):
        super().__init__(app)
        self.user_repository = UserRepository()
        self.agent_repository = AgentRepository()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip auth for public paths
        if (
            request.url.path in PUBLIC_PATHS
            or request.url.path.startswith(DOWNLOADS_PLUGINS_PATH_PREFIX)
            or request.url.path.startswith(A2A_WELL_KNOWN_PATH_PREFIX)
        ):
            return await call_next(request)

        # Skip auth for widget routes (handled by WidgetAuthMiddleware)
        if request.url.path.startswith(WIDGET_PATH_PREFIX):
            return await call_next(request)

        # Skip auth for A2A routes (handled by A2A auth dependencies where needed)
        if request.url.path.startswith(A2A_PATH_PREFIX):
            return await call_next(request)

        # Skip auth for the embeddable widget's HTML shell (public, scoped by widget key)
        if request.url.path.startswith(EMBED_PATH_PREFIX):
            return await call_next(request)

        # Skip auth for the public API (secret keys, checked by require_secret_key)
        if request.url.path.startswith(PUBLIC_API_PATH_PREFIX):
            return await call_next(request)

        # Skip auth for OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Every client sends the token as a header, SSE included (they stream over fetch, not EventSource).
        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid authorization header"}
            )

        is_expired, payload = decode_token(token, token_audiences_for(request.url.path))

        if payload is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token"}
            )

        if is_expired:
            return JSONResponse(
                status_code=401,
                content={"detail": "Token expired"}
            )

        email = payload.get("sub")
        user = self.user_repository.get_by_email(email) if email else None
        if not user:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token payload"}
            )

        if user.status in [UserStatus.INACTIVE.value, UserStatus.PENDING_DELETION.value]:
            return JSONResponse(
                status_code=403,
                content={"detail": "Account has been deactivated", "code": "ACCOUNT_INACTIVE"}
            )

        request.state.auth_token = token
        request.state.user_email = email
        analytics_agent_id = self._get_analytics_agent_id(request.url.path)
        if analytics_agent_id:
            agent = self.agent_repository.find_agent_by_id(analytics_agent_id, email)
            if not agent:
                return JSONResponse(
                    status_code=404,
                    content={"detail": "Agent not found"},
                )
            request.state.analytics_agent = agent

        return await call_next(request)

    def _get_analytics_agent_id(self, path: str) -> Optional[str]:
        """Extract analytics agent ID for analytics routes only."""
        if not path.startswith(ANALYTICS_AGENT_PATH_PREFIX):
            return None

        remainder = path.removeprefix(ANALYTICS_AGENT_PATH_PREFIX)
        if not remainder:
            return None

        agent_id = remainder.split("/", 1)[0].strip()
        return agent_id or None
