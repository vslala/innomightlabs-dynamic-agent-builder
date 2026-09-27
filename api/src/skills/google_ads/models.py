"""Google Ads skill models: credentials, install config, and action requests.

Every action argument that holds a list or object also accepts a JSON string, so an
automation action form (a text_area of JSON) and an agent (real JSON) share one model.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, field_validator, model_validator

MICROS = 1_000_000

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _from_json(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Expected JSON: {exc.msg}") from exc
    return value


def _flag(value: Any) -> Any:
    """Booleans arrive as "true"/"false" strings from install and action forms."""
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return value


Json = BeforeValidator(_from_json)
Flag = Annotated[bool, BeforeValidator(_flag)]


def customer_id_of(value: str) -> str:
    """A Google Ads customer id without dashes: "123-456-7890" -> "1234567890"."""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) != 10:
        raise ValueError(f"Google Ads customer ids have 10 digits; got '{value}'")
    return digits


def to_micros(amount: float) -> int:
    return int(round(float(amount) * MICROS))


def id_of(value: Any, label: str) -> str:
    digits = str(value or "").strip()
    if not digits.isdigit():
        raise ValueError(f"{label} must be a numeric id; got '{value}'")
    return digits


class GoogleAdsCredentials(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=1))
    scope: str = ""
    token_type: str = "Bearer"

    def is_expiring_soon(self, refresh_buffer_seconds: int = 60) -> bool:
        now = datetime.now(timezone.utc)
        return (self.expires_at - now).total_seconds() <= refresh_buffer_seconds

    def with_token_response(self, tokens: dict[str, Any]) -> "GoogleAdsCredentials":
        access_token = str(tokens.get("access_token") or self.access_token).strip()
        if not access_token:
            raise ValueError("Google Ads token response missing access_token")

        expires_in = int(tokens.get("expires_in") or 3600)
        return GoogleAdsCredentials(
            access_token=access_token,
            refresh_token=tokens.get("refresh_token") or self.refresh_token,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            scope=tokens.get("scope") or self.scope,
            token_type=tokens.get("token_type") or self.token_type or "Bearer",
        )


class GoogleAdsConfig(BaseModel):
    """The installed skill's configuration, and the limits it puts on every action."""

    customer_id: Optional[str] = None
    login_customer_id: Optional[str] = None
    access: Literal["read_only", "read_write"] = "read_only"
    max_daily_budget: Optional[float] = None
    allow_advanced_mutate: Flag = False

    @field_validator("customer_id", "login_customer_id", mode="before")
    @classmethod
    def _normalize_ids(cls, value: Any) -> Optional[str]:
        return customer_id_of(value) if value not in (None, "") else None

    @field_validator("max_daily_budget", mode="before")
    @classmethod
    def _blank_budget(cls, value: Any) -> Any:
        return None if value in (None, "") else value

    def customer(self, requested: Optional[str]) -> str:
        if requested:
            return customer_id_of(requested)
        if self.customer_id:
            return self.customer_id
        raise ValueError(
            "No Google Ads account given. Pass customer_id, or set a default account on the skill. "
            "list_accounts shows the accounts this connection can reach."
        )

    def require_writes(self) -> None:
        if self.access != "read_write":
            raise ValueError("The Google Ads skill is installed read-only. Reinstall it with read_write access to make changes.")
        if not self.max_daily_budget:
            raise ValueError("Set a maximum daily budget on the Google Ads skill before making changes.")

    def check_daily_budget(self, amount_micros: int) -> None:
        cap = to_micros(self.max_daily_budget or 0)
        if amount_micros > cap:
            raise ValueError(
                f"A daily budget of {amount_micros / MICROS:g} exceeds this skill's cap of {self.max_daily_budget:g}. "
                "Ask the user to raise the cap in the skill settings if they want to spend more."
            )


# --- shared pieces -----------------------------------------------------------------------------

DateRange = Literal[
    "TODAY", "YESTERDAY", "LAST_7_DAYS", "LAST_14_DAYS", "LAST_30_DAYS", "THIS_MONTH", "LAST_MONTH"
]
MatchType = Literal["EXACT", "PHRASE", "BROAD"]
Status = Literal["ENABLED", "PAUSED"]


class AccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: Optional[str] = None


class ReportWindow(AccountRequest):
    date_range: DateRange = "LAST_30_DAYS"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    limit: int = 25

    @model_validator(mode="after")
    def _bounds(self) -> "ReportWindow":
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("Pass both start_date and end_date, or neither")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        self.limit = max(1, min(200, int(self.limit)))
        return self

    def during(self) -> str:
        if self.start_date and self.end_date:
            return f"segments.date BETWEEN '{self.start_date.isoformat()}' AND '{self.end_date.isoformat()}'"
        return f"segments.date DURING {self.date_range}"


class WriteRequest(AccountRequest):
    """Every write previews first; apply needs the token the preview returned."""

    mode: Literal["preview", "apply"] = "preview"
    confirmation_token: Optional[str] = None


class KeywordSpec(BaseModel):
    text: Text
    match_type: MatchType = "PHRASE"
    max_cpc: Optional[float] = Field(default=None, gt=0)

    @field_validator("text")
    @classmethod
    def _length(cls, value: str) -> str:
        if len(value) > 80 or len(value.split()) > 10:
            raise ValueError(f"Keyword '{value}' is too long (max 80 characters and 10 words)")
        return value


class NegativeKeywordSpec(BaseModel):
    text: Text
    match_type: MatchType = "EXACT"


class ResponsiveSearchAdSpec(BaseModel):
    headlines: Annotated[list[Text], Json]
    descriptions: Annotated[list[Text], Json]
    final_url: Text
    path1: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=15)]] = None
    path2: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=15)]] = None
    status: Status = "ENABLED"

    @model_validator(mode="after")
    def _limits(self) -> "ResponsiveSearchAdSpec":
        if not 3 <= len(self.headlines) <= 15:
            raise ValueError("A responsive search ad needs 3 to 15 headlines")
        if not 2 <= len(self.descriptions) <= 4:
            raise ValueError("A responsive search ad needs 2 to 4 descriptions")
        too_long = [h for h in self.headlines if len(h) > 30] + [d for d in self.descriptions if len(d) > 90]
        if too_long:
            raise ValueError(f"Headlines are limited to 30 characters and descriptions to 90: {too_long}")
        if not self.final_url.startswith(("http://", "https://")):
            raise ValueError("final_url must be an absolute http(s) URL")
        return self


class AdGroupSpec(BaseModel):
    name: Text
    max_cpc: Optional[float] = Field(default=None, gt=0)
    keywords: Annotated[list[KeywordSpec], Json] = Field(default_factory=list)
    ads: Annotated[list[ResponsiveSearchAdSpec], Json] = Field(default_factory=list)


# --- reads -------------------------------------------------------------------------------------


class ListAccountsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manager_id: Optional[str] = None


class QueryRequest(AccountRequest):
    query: Text
    limit: int = 50

    @model_validator(mode="after")
    def _read_only(self) -> "QueryRequest":
        if not self.query.lstrip().upper().startswith("SELECT"):
            raise ValueError("query must be a GAQL SELECT statement")
        self.limit = max(1, min(200, int(self.limit)))
        return self


class DescribeFieldsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z_]+$")]
    contains: Optional[Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z_.]*$")]] = None
    limit: int = 60


class PerformanceRequest(ReportWindow):
    level: Literal["account", "campaign", "ad_group", "ad", "keyword"] = "campaign"
    metrics: Annotated[list[str], Json] = Field(
        default_factory=lambda: ["clicks", "impressions", "ctr", "cost", "conversions", "cost_per_conversion"]
    )
    campaign_id: Optional[str] = None
    ad_group_id: Optional[str] = None
    order_by: str = "cost"
    include_paused: Flag = True


class SearchTermsRequest(ReportWindow):
    campaign_id: Optional[str] = None
    ad_group_id: Optional[str] = None
    min_clicks: int = 0
    without_conversions: Flag = False


class ChangeHistoryRequest(AccountRequest):
    days: int = 7
    limit: int = 50

    @model_validator(mode="after")
    def _bounds(self) -> "ChangeHistoryRequest":
        # Google only keeps change events for 30 days.
        self.days = max(1, min(30, int(self.days)))
        self.limit = max(1, min(200, int(self.limit)))
        return self


class ListRequest(AccountRequest):
    campaign_id: Optional[str] = None
    ad_group_id: Optional[str] = None
    include_removed: Flag = False
    limit: int = 50

    @model_validator(mode="after")
    def _bounds(self) -> "ListRequest":
        self.limit = max(1, min(200, int(self.limit)))
        return self


class ListRecommendationsRequest(AccountRequest):
    types: Annotated[list[str], Json] = Field(default_factory=list)
    campaign_id: Optional[str] = None
    limit: int = 25


class KeywordIdeasRequest(AccountRequest):
    keywords: Annotated[list[Text], Json] = Field(default_factory=list)
    url: Optional[str] = None
    location_ids: Annotated[list[int], Json] = Field(default_factory=list)
    language_id: int = 1000
    limit: int = 25

    @model_validator(mode="after")
    def _seed(self) -> "KeywordIdeasRequest":
        if not self.keywords and not self.url:
            raise ValueError("Give seed keywords, a url, or both")
        self.limit = max(1, min(100, int(self.limit)))
        return self


# --- writes ------------------------------------------------------------------------------------


class CreateSearchCampaignRequest(WriteRequest):
    name: Text
    daily_budget: float = Field(gt=0)
    bidding_strategy: Literal["manual_cpc", "maximize_clicks", "maximize_conversions"] = "maximize_clicks"
    max_cpc: Optional[float] = Field(default=None, gt=0)
    location_ids: Annotated[list[int], Json] = Field(default_factory=list)
    language_ids: Annotated[list[int], Json] = Field(default_factory=list)
    include_search_partners: Flag = False
    ad_groups: Annotated[list[AdGroupSpec], Json] = Field(default_factory=list)
    start_enabled: Flag = False
    contains_eu_political_advertising: Flag = False


class UpdateCampaignRequest(WriteRequest):
    campaign_id: Text
    name: Optional[Text] = None
    include_search_partners: Optional[Flag] = None

    @model_validator(mode="after")
    def _something(self) -> "UpdateCampaignRequest":
        if self.name is None and self.include_search_partners is None:
            raise ValueError("Give at least one of name or include_search_partners")
        return self


class CampaignsRequest(WriteRequest):
    campaign_ids: Annotated[list[Text], Json]

    @field_validator("campaign_ids", mode="before")
    @classmethod
    def _one_or_many(cls, value: Any) -> Any:
        return [value] if isinstance(value, (int, str)) and not str(value).strip().startswith("[") else value

    @model_validator(mode="after")
    def _not_empty(self) -> "CampaignsRequest":
        if not self.campaign_ids:
            raise ValueError("campaign_ids must name at least one campaign")
        return self


class UpdateBudgetRequest(WriteRequest):
    campaign_id: Text
    daily_budget: float = Field(gt=0)


class RemoveCampaignRequest(WriteRequest):
    campaign_id: Text


class CreateAdGroupRequest(WriteRequest, AdGroupSpec):
    campaign_id: Text
    status: Status = "ENABLED"


class UpdateAdGroupRequest(WriteRequest):
    ad_group_id: Text
    name: Optional[Text] = None
    status: Optional[Status] = None
    max_cpc: Optional[float] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _something(self) -> "UpdateAdGroupRequest":
        if self.name is None and self.status is None and self.max_cpc is None:
            raise ValueError("Give at least one of name, status or max_cpc")
        return self


class AddKeywordsRequest(WriteRequest):
    ad_group_id: Text
    keywords: Annotated[list[KeywordSpec], Json] = Field(min_length=1)


class KeywordRef(BaseModel):
    ad_group_id: Text
    criterion_id: Text


class KeywordUpdate(KeywordRef):
    status: Optional[Status] = None
    max_cpc: Optional[float] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _something(self) -> "KeywordUpdate":
        if self.status is None and self.max_cpc is None:
            raise ValueError(f"Keyword {self.criterion_id}: give status, max_cpc, or both")
        return self


class UpdateKeywordsRequest(WriteRequest):
    keywords: Annotated[list[KeywordUpdate], Json] = Field(min_length=1)


class RemoveKeywordsRequest(WriteRequest):
    keywords: Annotated[list[KeywordRef], Json] = Field(min_length=1)


class AddNegativeKeywordsRequest(WriteRequest):
    campaign_id: Optional[str] = None
    ad_group_id: Optional[str] = None
    keywords: Annotated[list[NegativeKeywordSpec], Json] = Field(min_length=1)

    @model_validator(mode="after")
    def _one_level(self) -> "AddNegativeKeywordsRequest":
        if bool(self.campaign_id) == bool(self.ad_group_id):
            raise ValueError("Give exactly one of campaign_id or ad_group_id")
        return self


class CreateResponsiveSearchAdRequest(WriteRequest, ResponsiveSearchAdSpec):
    ad_group_id: Text


class AdRef(BaseModel):
    ad_group_id: Text
    ad_id: Text


class SetAdStatusRequest(WriteRequest):
    ads: Annotated[list[AdRef], Json] = Field(min_length=1)
    status: Status


class RecommendationsRequest(WriteRequest):
    resource_names: Annotated[list[Text], Json] = Field(min_length=1)


class MutateRequest(WriteRequest):
    operations: Annotated[list[dict[str, Any]], Json] = Field(min_length=1)
