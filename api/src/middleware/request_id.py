from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.logging.request_id import new_request_id, set_request_id


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a request id to each request/response and logging context."""

    header_name = "X-Request-Id"

    async def dispatch(self, request: Request, call_next):
        """Process an incoming HTTP request with request id propagation.
        
        Reads the request id from the configured inbound header when present, or
        generates a new one when the client did not supply one. The resolved id
        is attached to `request.state` so downstream handlers and route logic can
        access it during request processing.

        The method also pushes the request id into the logging context before
        invoking the next middleware or endpoint handler, ensuring log entries
        produced during the request can be correlated. The logging context is
        always cleared in a `finally` block to prevent the request id from
        leaking into unrelated work such as background tasks or subsequent
        requests.

        After the downstream application returns a response, the same request id
        is added to the outbound response headers so clients and operators can
        trace the full request/response lifecycle.
        """        
        
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
