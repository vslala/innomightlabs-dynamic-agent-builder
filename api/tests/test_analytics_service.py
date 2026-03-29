from datetime import UTC, datetime

from src.analytics.models import AnalyticsSource, TimeseriesBucket
from src.analytics.service import (
    ConversationRecord,
    floor_bucket_start,
    format_bucket_label,
    get_message_user_identity,
    iter_bucket_starts,
    percentile,
)
from src.messages.models import Message


def test_percentile_uses_expected_rank():
    values = [1, 2, 3, 4, 5]
    assert percentile(values, 50) == 3.0
    assert percentile(values, 90) == 5.0


def test_widget_user_identity_prefers_conversation_identity():
    record = ConversationRecord(
        conversation_id="conv-1",
        title="Widget Chat",
        source=AnalyticsSource.WIDGET,
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
        user_identity="visitor@example.com",
        messages=[],
    )
    message = Message(
        conversation_id="conv-1",
        created_by="fallback@example.com",
        role="user",
        content="hello",
        created_at=datetime(2026, 3, 1, 12, tzinfo=UTC),
    )
    assert get_message_user_identity(record, message) == "visitor@example.com"


def test_bucket_helpers_include_empty_buckets():
    from_local = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    to_local = datetime(2026, 3, 3, 9, 0, tzinfo=UTC)

    buckets = list(iter_bucket_starts(from_local, to_local, TimeseriesBucket.DAY))

    assert buckets == [
        datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
        datetime(2026, 3, 2, 0, 0, tzinfo=UTC),
        datetime(2026, 3, 3, 0, 0, tzinfo=UTC),
    ]
    assert floor_bucket_start(
        datetime(2026, 3, 5, 13, 0, tzinfo=UTC), TimeseriesBucket.WEEK
    ) == datetime(2026, 3, 2, 0, 0, tzinfo=UTC)
    assert format_bucket_label(datetime(2026, 3, 2, 0, 0, tzinfo=UTC), TimeseriesBucket.WEEK) == (
        "2026-03-02 week"
    )
