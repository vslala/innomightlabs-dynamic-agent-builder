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
from src.leads.errors import LeadsError
from src.vision.errors import ImageInputError

log = logging.getLogger(__name__)

GENERIC_ERROR_MESSAGE = "Something went wrong on our side. Please try again."


class UserFacingError(Exception):
    """An error whose message is written for the person using the app and safe to show anyone.

    Anything else that escapes is reported as GENERIC_ERROR_MESSAGE: exception text from
    DynamoDB, providers and upstream APIs stays in the logs.
    """


def client_error_message(exc: Exception) -> str:
    return str(exc) if isinstance(exc, UserFacingError) else GENERIC_ERROR_MESSAGE


def _validation_issues(exc: RequestValidationError) -> list[dict[str, object]]:
    """What was wrong and where, never the value: pydantic's `input` echoes whatever the client sent
    (tokens, passwords, API keys), and `ctx` can carry it too."""
    return [{key: issue[key] for key in ("type", "loc", "msg")} for issue in exc.errors()]


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

    @app.exception_handler(ImageInputError)
    async def image_input_error_handler(request: Request, exc: ImageInputError) -> JSONResponse:
        """An image was refused; `code` lets the client pick its own wording, `message` is fit to show."""
        log.warning(f"Image refused on {request.method} {request.url.path}: {exc.code}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": {"code": exc.code, "message": exc.message}, "path": request.url.path},
        )

    @app.exception_handler(LeadsError)
    async def leads_error_handler(request: Request, exc: LeadsError) -> JSONResponse:
        """Leads refused something; `code` lets the client pick its own wording, `message` is fit to show."""
        log.info(f"Leads refused {request.method} {request.url.path}: {exc.code}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": {"code": exc.code, "message": exc.message}, "path": request.url.path},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle request validation errors with detailed information."""
        issues = _validation_issues(exc)
        log.warning(f"Validation error on {request.method} {request.url.path}: {issues}")
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Validation error",
                "errors": issues,
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
