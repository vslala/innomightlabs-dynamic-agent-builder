"""Runtime environment helpers.

Keep environment detection and env-var lookups centralized so routers/services don't
sprinkle `os.environ.get(...)` checks everywhere.

Design goal:
- readable call sites (is_lambda(), aws_region())
- one place to tweak detection logic
"""

from __future__ import annotations

import os


def is_lambda() -> bool:
    """True when running inside AWS Lambda."""
    return bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))


def aws_region(default: str = "eu-west-2") -> str:
    """Return AWS region name with a sensible default for local dev."""
    return os.getenv("AWS_REGION_NAME", default)
