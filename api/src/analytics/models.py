"""Response and query models for analytics endpoints."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AnalyticsSource(str, Enum):
    DASHBOARD = "dashboard"
    WIDGET = "widget"


class TimeseriesMetric(str, Enum):
    MESSAGES = "messages"
    CONVERSATIONS = "conversations"
    UNIQUE_USERS = "unique_users"


class TimeseriesBucket(str, Enum):
    DAY = "day"
    WEEK = "week"


class AnalyticsWindow(BaseModel):
    from_at: datetime = Field(serialization_alias="from")
    to_at: datetime = Field(serialization_alias="to")
    tz: str
    sources: list[AnalyticsSource]


class AnalyticsMeta(BaseModel):
    truncated: bool
    truncation_reason: Optional[str] = None
    conversations_scanned: int
    messages_scanned: int


class AnalyticsTotals(BaseModel):
    conversations: int = 0
    messages: int = 0
    user_messages: int = 0
    assistant_messages: int = 0
    system_messages: int = 0
    unique_users: int = 0
    active_days: int = 0


class AnalyticsRatios(BaseModel):
    assistant_to_user: float = 0.0
    dropoff_rate: float = 0.0
    zero_assistant_conversation_rate: float = 0.0


class AnalyticsPercentiles(BaseModel):
    avg: float = 0.0
    p50: float = 0.0
    p90: float = 0.0


class AnalyticsDistribution(BaseModel):
    messages_per_conversation: AnalyticsPercentiles
    assistant_messages_per_conversation: AnalyticsPercentiles


class TopConversation(BaseModel):
    conversation_id: str
    title: str
    source: AnalyticsSource
    messages: int


class TopUser(BaseModel):
    user: str
    source: AnalyticsSource
    messages: int


class AnalyticsTop(BaseModel):
    longest_conversations: list[TopConversation]
    most_active_users: list[TopUser]


class AnalyticsOverviewResponse(BaseModel):
    agent_id: str
    window: AnalyticsWindow
    totals: AnalyticsTotals
    ratios: AnalyticsRatios
    distribution: AnalyticsDistribution
    top: AnalyticsTop
    breakdown_by_source: dict[AnalyticsSource, AnalyticsTotals]
    meta: AnalyticsMeta


class TimeseriesPoint(BaseModel):
    bucket_start: datetime
    bucket_label: str
    value: int
    source: Optional[AnalyticsSource] = None


class AnalyticsTimeseriesResponse(BaseModel):
    agent_id: str
    window: AnalyticsWindow
    metric: TimeseriesMetric
    bucket: TimeseriesBucket
    series: list[TimeseriesPoint]
    meta: AnalyticsMeta
