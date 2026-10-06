"""Runtime environment helpers.

Keep environment detection and env-var lookups centralized so routers/services don't
sprinkle `os.environ.get(...)` checks everywhere.

Design goal:
- readable call sites (is_lambda())
- one place to tweak detection logic
"""

from __future__ import annotations

import os


def is_lambda() -> bool:
    """True when running inside AWS Lambda."""
    return bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))

