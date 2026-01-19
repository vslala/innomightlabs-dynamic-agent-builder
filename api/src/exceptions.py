"""
Global exception handlers for the FastAPI application.

Provides consistent JSON error responses and logging for all exceptions.
"""

import logging
import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register all global exception handlers on the FastAPI app.

    Call this after creating the FastAPI app instance.
    """

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """Handle HTTP exceptions with consistent JSON format."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "path": request.url.path,
            },
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

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        Global exception handler that:
        1. Logs the full stack trace for debugging
        2. Returns a clean JSON error response to the client
        """
        log.error(
            f"Unhandled exception on {request.method} {request.url.path}: {exc}\n"
            f"Stack trace:\n{traceback.format_exc()}"
        )

        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "error_type": exc.__class__.__name__,
                "message": str(exc),
                "path": request.url.path,
            },
        )
