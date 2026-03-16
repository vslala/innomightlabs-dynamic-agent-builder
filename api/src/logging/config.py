"""Logging configuration.

Goals:
- consistent format locally + in Lambda
- include request_id when available
- keep setup in one place (avoid ad-hoc logging config in main.py)
"""

from __future__ import annotations

import logging
import os

from src.logging.request_id import RequestIdFilter


def configure_logging() -> None:
    # If something already configured root handlers (e.g. uvicorn), don't fight it.
    root = logging.getLogger()

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root.setLevel(level)

    log_format = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"

    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(log_format))
        root.addHandler(handler)
    else:
        for h in root.handlers:
            if h.formatter is None:
                h.setFormatter(logging.Formatter(log_format))

    # Ensure request_id is always present on records.
    request_filter = RequestIdFilter()

    # Attach to handlers (covers all loggers that propagate to root).
    for h in root.handlers:
        h.addFilter(request_filter)

    # Also attach to common loggers for completeness.
    for logger_name in ("", "uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(logger_name).addFilter(request_filter)
