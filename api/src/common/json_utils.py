"""JSON utilities.

DynamoDB often returns numbers as Decimal. This helper provides a safe json.dumps
wrapper that can serialize Decimal (and a few other common types) without
crashing.

Use for logging/debug contexts (never for secrets).
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any


def _default(o: Any):
    if isinstance(o, Decimal):
        # Preserve ints when possible, otherwise float
        try:
            if o == o.to_integral_value():
                return int(o)
        except Exception:
            pass
        return float(o)

    if isinstance(o, datetime):
        return o.isoformat()

    return str(o)


def dumps_safe(obj: Any, *, ensure_ascii: bool = False) -> str:
    return json.dumps(obj, ensure_ascii=ensure_ascii, default=_default)
