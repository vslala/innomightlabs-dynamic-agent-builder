"""Time helpers shared across modules."""

from datetime import datetime, timezone


def as_aware_utc(value: datetime) -> datetime:
    """Interpret a naive datetime as UTC; convert an aware one to UTC.

    Persisted timestamps come back naive from some stores and aware from
    others, and subtracting the two raises. Every staleness check needs this,
    so it lives in one place.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
