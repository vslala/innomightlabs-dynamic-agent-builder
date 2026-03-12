from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.logging.request_id import new_request_id, set_request_id


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a request id to each request/response and logging context."""

    header_name = "X-Request-Id"

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(self.header_name) or new_request_id()

        # store on request for handlers to use
        request.state.request_id = request_id

        # store in logging context
        set_request_id(request_id)
        try:
            response: Response = await call_next(request)
        finally:
            # avoid leaking into background tasks
            set_request_id(None)

        response.headers[self.header_name] = request_id
        return response
