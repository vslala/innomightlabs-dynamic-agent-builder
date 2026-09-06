from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TokenUsagePeriod(str, Enum):
    """Pre-aggregated bucket granularity for token usage records.

    Deliberately not an extension of analytics/models.py::TimeseriesBucket
    (day/week) -- that enum's bucketing helpers in analytics/service.py are
    calendar-week-aware for on-the-fly scanning of conversations, a different
    aggregation model than the pre-aggregated day/month/year buckets used here.
    """

    DAY = "day"
    MONTH = "month"
    YEAR = "year"


def format_period_key(period: TokenUsagePeriod, moment: datetime) -> str:
    """Format a moment as the sort-key suffix for the given bucket granularity."""
    if period == TokenUsagePeriod.DAY:
        return moment.strftime("%Y-%m-%d")
    if period == TokenUsagePeriod.MONTH:
        return moment.strftime("%Y-%m")
    return moment.strftime("%Y")


@dataclass
class TokenUsageRecord:
    """A single pre-aggregated (agent_id, period, period_key, llm_model) bucket.

    Key scheme:
        pk = f"Agent#{agent_id}"
        sk = f"TokenUsage#{period}#{period_key}#{llm_model}"

    period_key is formatted as YYYY-MM-DD / YYYY-MM / YYYY depending on period.
    Putting period_key before llm_model in the sort key means one Query
    (pk + sk BETWEEN) returns all models' buckets for a date range in one call.

    Only ever constructed by from_dynamo_item -- writes go through
    TokenUsageRepository's atomic update_item calls, not this dataclass.
    """

    agent_id: str
    period: TokenUsagePeriod
    period_key: str
    llm_model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_dynamo_item(cls, item: dict) -> "TokenUsageRecord":
        return cls(
            agent_id=item["agent_id"],
            period=TokenUsagePeriod(item["period"]),
            period_key=item["period_key"],
            llm_model=item["llm_model"],
            prompt_tokens=int(item.get("prompt_tokens", 0)),
            completion_tokens=int(item.get("completion_tokens", 0)),
            total_tokens=int(item.get("total_tokens", 0)),
            call_count=int(item.get("call_count", 0)),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
        )


class TokenUsagePoint(BaseModel):
    period_key: str
    period_start: datetime
    llm_model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    call_count: int


class TokenUsageTimeseriesResponse(BaseModel):
    agent_id: str
    period: TokenUsagePeriod
    from_at: datetime = Field(serialization_alias="from")
    to_at: datetime = Field(serialization_alias="to")
    llm_model_filter: Optional[str] = None
    series: list[TokenUsagePoint]
