"""JSON logging configuration for AWS CloudWatch."""

import json
import logging
import traceback
from datetime import datetime
from typing import Any


class CloudWatchJsonFormatter(logging.Formatter):
    """
    JSON formatter that outputs single-line logs for CloudWatch.

    Formats log records as JSON with all fields on a single line,
    including stack traces and exception information.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as single-line JSON."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        # Add exception information if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": "".join(traceback.format_exception(*record.exc_info)),
            }

        # Add stack trace if present
        if record.stack_info:
            log_data["stack_trace"] = record.stack_info

        # Add source location
        log_data["source"] = {
            "file": record.pathname,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Convert to single-line JSON
        return json.dumps(log_data, ensure_ascii=False, separators=(",", ":"))


def configure_cloudwatch_logging(log_level: str = "INFO") -> None:
    """
    Configure logging for AWS CloudWatch with JSON formatting.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler with JSON formatter
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(CloudWatchJsonFormatter())
    root_logger.addHandler(console_handler)

    # Suppress noisy libraries
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
