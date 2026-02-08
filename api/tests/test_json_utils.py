from datetime import datetime, timezone
from decimal import Decimal

from src.common.json_utils import dumps_safe


def test_dumps_safe_serializes_decimal_and_datetime():
    s = dumps_safe({"n": Decimal("10"), "x": Decimal("1.25"), "t": datetime(2026, 1, 1, tzinfo=timezone.utc)})
    assert '"n": 10' in s
    assert '"x": 1.25' in s
    assert '"t": "2026-01-01T00:00:00+00:00"' in s
