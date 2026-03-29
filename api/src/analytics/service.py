"""Analytics aggregation service for per-agent dashboard APIs."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil
from statistics import median
from typing import Iterable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException

from src.analytics.models import (
    AnalyticsDistribution,
    AnalyticsMeta,
    AnalyticsOverviewResponse,
    AnalyticsPercentiles,
    AnalyticsRatios,
    AnalyticsSource,
    AnalyticsTimeseriesResponse,
    AnalyticsTop,
    AnalyticsTotals,
    AnalyticsWindow,
    TimeseriesBucket,
    TimeseriesMetric,
    TimeseriesPoint,
    TopConversation,
    TopUser,
)
from src.conversations.repository import ConversationRepository
from src.messages.models import Message
from src.messages.repository import MessageRepository
from src.widget.repository import WidgetConversationRepository

DEFAULT_WINDOW_DAYS = 30
MAX_WINDOW_DAYS = 90
MAX_CONVERSATIONS_SCANNED = 500
MAX_MESSAGES_SCANNED = 10_000
TOP_RESULTS_LIMIT = 5
WIDGET_PAGE_SIZE = 100


@dataclass
class AnalyticsContext:
    agent_id: str
    owner_email: str
    window: AnalyticsWindow
    timezone: ZoneInfo
    sources: list[AnalyticsSource]
    conversation_records: list["ConversationRecord"]
    truncated: bool = False
    truncation_reason: Optional[str] = None
    conversations_scanned: int = 0
    messages_scanned: int = 0


@dataclass
class ConversationRecord:
    conversation_id: str
    title: str
    source: AnalyticsSource
    created_at: datetime
    user_identity: Optional[str] = None
    messages: list[Message] | None = None


class AnalyticsService:
    def __init__(
        self,
        *,
        conversation_repository: Optional[ConversationRepository] = None,
        widget_conversation_repository: Optional[WidgetConversationRepository] = None,
        message_repository: Optional[MessageRepository] = None,
    ) -> None:
        self.conversation_repository = conversation_repository or ConversationRepository()
        self.widget_conversation_repository = (
            widget_conversation_repository or WidgetConversationRepository()
        )
        self.message_repository = message_repository or MessageRepository()

    def get_overview(
        self,
        *,
        owner_email: str,
        agent_id: str,
        from_at: Optional[datetime],
        to_at: Optional[datetime],
        tz_name: str,
        sources: Optional[list[AnalyticsSource]],
    ) -> AnalyticsOverviewResponse:
        context = self._build_context(
            owner_email=owner_email,
            agent_id=agent_id,
            from_at=from_at,
            to_at=to_at,
            tz_name=tz_name,
            sources=sources,
        )

        totals = self._build_totals(context.conversation_records, context.timezone)
        source_breakdown = {
            source: self._build_totals(
                [record for record in context.conversation_records if record.source == source],
                context.timezone,
            )
            for source in context.sources
        }

        ratios = self._build_ratios(context.conversation_records, totals)
        distribution = AnalyticsDistribution(
            messages_per_conversation=self._build_percentiles(
                len(record.messages or []) for record in context.conversation_records
            ),
            assistant_messages_per_conversation=self._build_percentiles(
                sum(1 for message in record.messages or [] if message.role == "assistant")
                for record in context.conversation_records
            ),
        )
        top = AnalyticsTop(
            longest_conversations=self._build_top_conversations(context.conversation_records),
            most_active_users=self._build_top_users(context.conversation_records),
        )

        return AnalyticsOverviewResponse(
            agent_id=agent_id,
            window=context.window,
            totals=totals,
            ratios=ratios,
            distribution=distribution,
            top=top,
            breakdown_by_source=source_breakdown,
            meta=self._build_meta(context),
        )

    def get_timeseries(
        self,
        *,
        owner_email: str,
        agent_id: str,
        metric: TimeseriesMetric,
        bucket: TimeseriesBucket,
        from_at: Optional[datetime],
        to_at: Optional[datetime],
        tz_name: str,
        sources: Optional[list[AnalyticsSource]],
    ) -> AnalyticsTimeseriesResponse:
        context = self._build_context(
            owner_email=owner_email,
            agent_id=agent_id,
            from_at=from_at,
            to_at=to_at,
            tz_name=tz_name,
            sources=sources,
        )

        bucket_starts = list(
            iter_bucket_starts(
                context.window.from_at.astimezone(context.timezone),
                context.window.to_at.astimezone(context.timezone),
                bucket,
            )
        )
        series = self._build_timeseries(
            records=context.conversation_records,
            bucket_starts=bucket_starts,
            metric=metric,
            bucket=bucket,
            timezone=context.timezone,
            include_source=len(context.sources) > 1,
        )

        return AnalyticsTimeseriesResponse(
            agent_id=agent_id,
            window=context.window,
            metric=metric,
            bucket=bucket,
            series=series,
            meta=self._build_meta(context),
        )

    def _build_context(
        self,
        *,
        owner_email: str,
        agent_id: str,
        from_at: Optional[datetime],
        to_at: Optional[datetime],
        tz_name: str,
        sources: Optional[list[AnalyticsSource]],
    ) -> AnalyticsContext:
        timezone = parse_timezone(tz_name)
        normalized_from, normalized_to = normalize_window(from_at, to_at)
        validate_window(normalized_from, normalized_to)

        selected_sources = sources or [AnalyticsSource.DASHBOARD, AnalyticsSource.WIDGET]
        context = AnalyticsContext(
            agent_id=agent_id,
            owner_email=owner_email,
            timezone=timezone,
            sources=selected_sources,
            conversation_records=[],
            window=AnalyticsWindow(
                from_at=normalized_from,
                to_at=normalized_to,
                tz=tz_name,
                sources=selected_sources,
            ),
        )

        self._collect_conversations(context)
        self._collect_messages(context)
        return context

    def _collect_conversations(self, context: AnalyticsContext) -> None:
        window_from = context.window.from_at
        window_to = context.window.to_at

        if AnalyticsSource.DASHBOARD in context.sources:
            conversations = self.conversation_repository.find_all_by_user(context.owner_email)
            for conversation in conversations:
                if context.conversations_scanned >= MAX_CONVERSATIONS_SCANNED:
                    self._truncate(context, "conversation scan limit reached")
                    break
                if conversation.agent_id != context.agent_id:
                    continue
                if not within_window(conversation.created_at, window_from, window_to):
                    continue
                context.conversation_records.append(
                    ConversationRecord(
                        conversation_id=conversation.conversation_id,
                        title=conversation.title,
                        source=AnalyticsSource.DASHBOARD,
                        created_at=conversation.created_at,
                    )
                )
                context.conversations_scanned += 1

        if AnalyticsSource.WIDGET in context.sources and not context.truncated:
            cursor: Optional[str] = None
            has_more = True
            while has_more and not context.truncated:
                conversations, cursor, has_more = self.widget_conversation_repository.find_by_agent(
                    context.agent_id,
                    limit=WIDGET_PAGE_SIZE,
                    cursor=cursor,
                )
                for conversation in conversations:
                    if context.conversations_scanned >= MAX_CONVERSATIONS_SCANNED:
                        self._truncate(context, "conversation scan limit reached")
                        break
                    if not within_window(conversation.created_at, window_from, window_to):
                        continue
                    context.conversation_records.append(
                        ConversationRecord(
                            conversation_id=conversation.conversation_id,
                            title=conversation.title,
                            source=AnalyticsSource.WIDGET,
                            created_at=conversation.created_at,
                            user_identity=conversation.visitor_email,
                        )
                    )
                    context.conversations_scanned += 1

    def _collect_messages(self, context: AnalyticsContext) -> None:
        for record in context.conversation_records:
            if context.truncated and context.messages_scanned >= MAX_MESSAGES_SCANNED:
                break

            conversation_messages = self.message_repository.find_by_conversation(record.conversation_id)
            filtered_messages: list[Message] = []
            for message in conversation_messages:
                if not within_window(message.created_at, context.window.from_at, context.window.to_at):
                    continue
                if context.messages_scanned >= MAX_MESSAGES_SCANNED:
                    self._truncate(context, "message scan limit reached")
                    break
                filtered_messages.append(message)
                context.messages_scanned += 1

            record.messages = filtered_messages
            if context.truncated and context.messages_scanned >= MAX_MESSAGES_SCANNED:
                break

    def _build_totals(
        self,
        records: list[ConversationRecord],
        timezone: ZoneInfo,
    ) -> AnalyticsTotals:
        totals = AnalyticsTotals(conversations=len(records))
        unique_users: set[str] = set()
        active_days: set[str] = set()

        for record in records:
            for message in record.messages or []:
                totals.messages += 1
                if message.role == "user":
                    totals.user_messages += 1
                elif message.role == "assistant":
                    totals.assistant_messages += 1
                elif message.role == "system":
                    totals.system_messages += 1

                user_id = get_message_user_identity(record, message)
                if user_id:
                    unique_users.add(user_id)
                active_days.add(message.created_at.astimezone(timezone).date().isoformat())

        totals.unique_users = len(unique_users)
        totals.active_days = len(active_days)
        return totals

    def _build_ratios(
        self,
        records: list[ConversationRecord],
        totals: AnalyticsTotals,
    ) -> AnalyticsRatios:
        user_message_conversations = 0
        zero_assistant_conversations = 0
        for record in records:
            user_count = sum(1 for message in record.messages or [] if message.role == "user")
            assistant_count = sum(
                1 for message in record.messages or [] if message.role == "assistant"
            )
            if user_count > 0:
                user_message_conversations += 1
                if assistant_count == 0:
                    zero_assistant_conversations += 1

        assistant_to_user = (
            round(totals.assistant_messages / totals.user_messages, 4)
            if totals.user_messages
            else 0.0
        )
        dropoff_rate = (
            round(zero_assistant_conversations / user_message_conversations, 4)
            if user_message_conversations
            else 0.0
        )
        zero_assistant_rate = (
            round(zero_assistant_conversations / len(records), 4) if records else 0.0
        )
        return AnalyticsRatios(
            assistant_to_user=assistant_to_user,
            dropoff_rate=dropoff_rate,
            zero_assistant_conversation_rate=zero_assistant_rate,
        )

    def _build_top_conversations(
        self, records: list[ConversationRecord]
    ) -> list[TopConversation]:
        ranked = sorted(
            records,
            key=lambda record: (len(record.messages or []), record.created_at),
            reverse=True,
        )
        return [
            TopConversation(
                conversation_id=record.conversation_id,
                title=record.title,
                source=record.source,
                messages=len(record.messages or []),
            )
            for record in ranked[:TOP_RESULTS_LIMIT]
        ]

    def _build_top_users(self, records: list[ConversationRecord]) -> list[TopUser]:
        counter: Counter[tuple[AnalyticsSource, str]] = Counter()
        for record in records:
            for message in record.messages or []:
                identity = get_message_user_identity(record, message)
                if identity:
                    counter[(record.source, identity)] += 1

        ranked = counter.most_common(TOP_RESULTS_LIMIT)
        return [
            TopUser(user=user, source=source, messages=count)
            for (source, user), count in ranked
        ]

    def _build_timeseries(
        self,
        *,
        records: list[ConversationRecord],
        bucket_starts: list[datetime],
        metric: TimeseriesMetric,
        bucket: TimeseriesBucket,
        timezone: ZoneInfo,
        include_source: bool,
    ) -> list[TimeseriesPoint]:
        base_keys = [
            (source if include_source else None, bucket_start)
            for source in (
                sorted({record.source for record in records}, key=lambda value: value.value)
                if include_source
                else [None]
            )
            for bucket_start in bucket_starts
        ]

        counts: dict[tuple[Optional[AnalyticsSource], datetime], int] = {
            key: 0 for key in base_keys
        }

        if metric == TimeseriesMetric.UNIQUE_USERS:
            unique_buckets: dict[tuple[Optional[AnalyticsSource], datetime], set[str]] = defaultdict(set)
            for record in records:
                source_key = record.source if include_source else None
                for message in record.messages or []:
                    identity = get_message_user_identity(record, message)
                    if not identity:
                        continue
                    bucket_start = floor_bucket_start(message.created_at.astimezone(timezone), bucket)
                    unique_buckets[(source_key, bucket_start)].add(identity)
            for key, users in unique_buckets.items():
                counts[key] = len(users)
        elif metric == TimeseriesMetric.CONVERSATIONS:
            for record in records:
                source_key = record.source if include_source else None
                bucket_start = floor_bucket_start(record.created_at.astimezone(timezone), bucket)
                counts[(source_key, bucket_start)] = counts.get((source_key, bucket_start), 0) + 1
        else:
            for record in records:
                source_key = record.source if include_source else None
                for message in record.messages or []:
                    bucket_start = floor_bucket_start(message.created_at.astimezone(timezone), bucket)
                    counts[(source_key, bucket_start)] = counts.get((source_key, bucket_start), 0) + 1

        series: list[TimeseriesPoint] = []
        for key in sorted(counts.keys(), key=lambda item: ((item[0] or "").value if item[0] else "", item[1])):
            source_key, bucket_start = key
            series.append(
                TimeseriesPoint(
                    bucket_start=bucket_start,
                    bucket_label=format_bucket_label(bucket_start, bucket),
                    value=counts[key],
                    source=source_key,
                )
            )
        return series

    def _truncate(self, context: AnalyticsContext, reason: str) -> None:
        context.truncated = True
        if context.truncation_reason is None:
            context.truncation_reason = reason

    def _build_meta(self, context: AnalyticsContext) -> AnalyticsMeta:
        return AnalyticsMeta(
            truncated=context.truncated,
            truncation_reason=context.truncation_reason,
            conversations_scanned=context.conversations_scanned,
            messages_scanned=context.messages_scanned,
        )

    def _build_percentiles(self, values: Iterable[int]) -> AnalyticsPercentiles:
        numeric_values = list(values)
        if not numeric_values:
            return AnalyticsPercentiles()

        numeric_values.sort()
        average = round(sum(numeric_values) / len(numeric_values), 2)
        return AnalyticsPercentiles(
            avg=average,
            p50=percentile(numeric_values, 50),
            p90=percentile(numeric_values, 90),
        )


def parse_timezone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid timezone '{tz_name}'") from exc


def normalize_window(
    from_at: Optional[datetime], to_at: Optional[datetime]
) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    normalized_to = ensure_utc(to_at) if to_at else now
    normalized_from = ensure_utc(from_at) if from_at else normalized_to - timedelta(days=DEFAULT_WINDOW_DAYS)
    return normalized_from, normalized_to


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def validate_window(from_at: datetime, to_at: datetime) -> None:
    if from_at >= to_at:
        raise HTTPException(status_code=400, detail="'from' must be earlier than 'to'")
    if to_at - from_at > timedelta(days=MAX_WINDOW_DAYS):
        raise HTTPException(
            status_code=400,
            detail=f"Window cannot exceed {MAX_WINDOW_DAYS} days",
        )


def within_window(value: datetime, from_at: datetime, to_at: datetime) -> bool:
    normalized = ensure_utc(value)
    return from_at <= normalized < to_at


def percentile(values: list[int], pct: int) -> float:
    if not values:
        return 0.0
    if pct == 50:
        return float(median(values))

    position = ceil((pct / 100) * len(values)) - 1
    position = max(0, min(position, len(values) - 1))
    return float(values[position])


def get_message_user_identity(record: ConversationRecord, message: Message) -> Optional[str]:
    if record.source == AnalyticsSource.WIDGET:
        return record.user_identity or message.created_by or None
    return message.created_by or None


def floor_bucket_start(value: datetime, bucket: TimeseriesBucket) -> datetime:
    if bucket == TimeseriesBucket.DAY:
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    start = value - timedelta(days=value.weekday())
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def iter_bucket_starts(
    from_local: datetime,
    to_local: datetime,
    bucket: TimeseriesBucket,
) -> Iterable[datetime]:
    current = floor_bucket_start(from_local, bucket)
    end = floor_bucket_start(to_local, bucket)
    step = timedelta(days=1 if bucket == TimeseriesBucket.DAY else 7)

    while current <= end:
        yield current
        current += step


def format_bucket_label(bucket_start: datetime, bucket: TimeseriesBucket) -> str:
    if bucket == TimeseriesBucket.DAY:
        return bucket_start.strftime("%Y-%m-%d")
    return f"{bucket_start.strftime('%Y-%m-%d')} week"
