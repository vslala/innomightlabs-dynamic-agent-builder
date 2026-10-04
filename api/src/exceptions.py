"""
Global exception handlers for the FastAPI application.

Provides consistent JSON error responses and logging for all exceptions.
"""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.common.pagination import InvalidCursor
from src.logging.request_id import get_request_id

log = logging.getLogger(__name__)

GENERIC_ERROR_MESSAGE = "Something went wrong on our side. Please try again."


class UserFacingError(Exception):
    """An error whose message is written for the person using the app and safe to show anyone.

    Anything else that escapes is reported as GENERIC_ERROR_MESSAGE: exception text from
    DynamoDB, providers and upstream APIs stays in the logs.
    """


def client_error_message(exc: Exception) -> str:
    return str(exc) if isinstance(exc, UserFacingError) else GENERIC_ERROR_MESSAGE


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None) or get_request_id()


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register all global exception handlers on the FastAPI app.

    Call this after creating the FastAPI app instance.
    """

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """Handle HTTP exceptions with consistent JSON format."""
        # Log client errors (4xx) at warning level, server errors (5xx) at error level
        if exc.status_code >= 500:
            log.error(
                f"HTTP {exc.status_code} on {request.method} {request.url.path}: {exc.detail}"
            )
        elif exc.status_code >= 400:
            log.warning(
                f"HTTP {exc.status_code} on {request.method} {request.url.path}: {exc.detail}"
            )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "path": request.url.path,
            },
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle request validation errors with detailed information."""
        log.warning(
            f"Validation error on {request.method} {request.url.path}: {exc.errors()}"
        )
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Validation error",
                "errors": exc.errors(),
                "path": request.url.path,
            },
        )

    @app.exception_handler(InvalidCursor)
    async def invalid_cursor_handler(request: Request, exc: InvalidCursor) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc), "path": request.url.path})

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Log everything; tell the client only that it failed, and which request to look up."""
        request_id = _request_id(request)
        log.error(
            "Unhandled exception on %s %s (request %s): %s",
            request.method, request.url.path, request_id, exc, exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": GENERIC_ERROR_MESSAGE, "request_id": request_id, "path": request.url.path},
            headers={"X-Request-Id": request_id} if request_id else None,
        )
