"""
Widget authentication middleware.

Handles API key validation and visitor JWT authentication for widget endpoints.
"""

import logging
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from src.apikeys.repository import ApiKeyRepository

log = logging.getLogger(__name__)


class WidgetAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware for widget API key authentication.

    Validates X-API-Key header and checks origin against allowed_origins.
    Sets request.state.api_key and request.state.agent_id for downstream handlers.
    """

    API_KEY_HEADER = "X-API-Key"

    def __init__(self, app, api_key_repo: Optional[ApiKeyRepository] = None):
        super().__init__(app)
        self.api_key_repo = api_key_repo or ApiKeyRepository()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Only apply to widget routes
        if not request.url.path.startswith("/widget"):
            return await call_next(request)

        # Skip auth for OAuth routes (they handle their own auth via state)
        if request.url.path in ["/widget/auth/google", "/widget/auth/callback", "/widget/auth/callback-page"]:
            return await call_next(request)

        # Validate API key for all widget routes (including /widget/config)
        try:
            await self._validate_api_key(request)
        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail},
            )
        except Exception as e:
            log.error(f"Widget auth middleware error: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"detail": f"Internal server error: {str(e)}"},
            )

        return await call_next(request)

    async def _validate_api_key(self, request: Request) -> None:
        """Validate API key from header and set request state."""
        api_key_header = request.headers.get(self.API_KEY_HEADER)

        if not api_key_header:
            raise HTTPException(
                status_code=401,
                detail="Missing X-API-Key header",
            )

        # Look up API key
        api_key = self.api_key_repo.find_by_public_key(api_key_header)

        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key",
            )

        if not api_key.is_active:
            raise HTTPException(
                status_code=401,
                detail="API key is disabled",
            )

        # Check origin if allowed_origins is set
        origin = request.headers.get("Origin")
        if not api_key.is_origin_allowed(origin):
            log.warning(
                f"Origin '{origin}' not allowed for API key {api_key.key_id}"
            )
            raise HTTPException(
                status_code=403,
                detail=f"Origin '{origin}' is not allowed for this API key",
            )

        # Set request state for downstream handlers
        request.state.api_key = api_key
        request.state.agent_id = api_key.agent_id

        # Increment usage counter (fire and forget)
        try:
            self.api_key_repo.increment_request_count(
                api_key.agent_id, api_key.key_id
            )
        except Exception as e:
            log.error(f"Failed to increment request count: {e}")


def get_api_key_from_request(request: Request):
    """
    Dependency to get validated API key from request state.

    Use this in widget route handlers after WidgetAuthMiddleware has run.
    """
    api_key = getattr(request.state, "api_key", None)
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key not validated",
        )
    return api_key


def get_agent_id_from_request(request: Request) -> str:
    """
    Dependency to get agent ID from validated API key.

    Use this in widget route handlers after WidgetAuthMiddleware has run.
    """
    agent_id = getattr(request.state, "agent_id", None)
    if not agent_id:
        raise HTTPException(
            status_code=401,
            detail="Agent ID not available",
        )
    return str(agent_id)
