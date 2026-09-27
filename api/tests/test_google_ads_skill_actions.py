"""Google Ads skill actions against a fake Google Ads REST API (the only external boundary)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx
import pytest

from src.crypto import encrypt
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from src.skills.google_ads import accounts, ads, campaigns, keywords, mutate, recommendations, reporting
from src.skills.google_ads.client import GoogleAdsError
from src.skills.google_ads.models import GoogleAdsCredentials
from src.skills.registry import SkillRegistry

OWNER = "owner@example.com"
CUSTOMER = "1234567890"
AGENT_CONTEXT = {"owner_email": OWNER, "installed_skill_id": "google_ads", "conversation_id": "c1"}
AUTOMATION_CONTEXT = {"owner_email": OWNER, "conversation_id": "c2", "automation_run_id": "run-1"}
READ_WRITE = {"customer_id": "123-456-7890", "access": "read_write", "max_daily_budget": "50"}
READ_ONLY = {"customer_id": "123-456-7890", "access": "read_only"}


class FakeGoogleAds:
    """Records requests; answers with queued responses, or {} by default."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.responses: list[httpx.Response] = []

    def respond(self, payload: dict[str, Any], status: int = 200) -> None:
        self.responses.append(httpx.Response(status, json=payload))

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses.pop(0) if self.responses else httpx.Response(200, json={})

    def body(self, index: int = -1) -> dict[str, Any]:
        return json.loads(self.requests[index].content)


@pytest.fixture
def google(monkeypatch, dynamodb_table) -> FakeGoogleAds:
    fake = FakeGoogleAds()
    monkeypatch.setattr(
        "src.skills.google_ads.client._http_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)),
    )
    ProviderSettingsRepository().save(
        ProviderSettings(
            user_email=OWNER,
            provider_name="GoogleAds",
            encrypted_credentials=encrypt(
                GoogleAdsCredentials(access_token="access", refresh_token="refresh").model_dump_json()
            ),
            auth_type="oauth",
        )
    )
    return fake


def run(handler: Callable, arguments: dict[str, Any], config: dict[str, Any] = READ_WRITE, context=AGENT_CONTEXT) -> Any:
    return asyncio.run(handler(arguments=arguments, config=config, context=context))


# --- reads -------------------------------------------------------------------------------------


def test_performance_report_builds_gaql_and_returns_money_in_currency_units(google):
    google.respond(
        {
            "results": [
                {
                    "customer": {"currencyCode": "GBP", "resourceName": "customers/1234567890"},
                    "campaign": {"id": "11", "name": "Shoes", "status": "ENABLED", "resourceName": "customers/1/campaigns/11"},
                    "adGroup": {"id": "22", "name": "Running"},
                    "adGroupCriterion": {"criterionId": "33", "keyword": {"text": "running shoes", "matchType": "PHRASE"}},
                    "metrics": {"clicks": "120", "costMicros": "45670000", "costPerConversion": 5700000.5},
                }
            ]
        }
    )

    report = run(
        reporting.get_performance,
        {"level": "keyword", "campaign_id": "11", "date_range": "LAST_7_DAYS", "metrics": '["clicks","cost","cost_per_conversion"]', "limit": "1"},
        READ_ONLY,
    )

    request = google.requests[0]
    assert request.url.path == "/v25/customers/1234567890/googleAds:search"
    assert request.headers["authorization"] == "Bearer access"
    assert "developer-token" not in request.headers
    gaql = google.body()["query"]
    assert "FROM keyword_view" in gaql
    assert "segments.date DURING LAST_7_DAYS" in gaql
    assert "campaign.id = 11" in gaql
    assert "ORDER BY metrics.cost_micros DESC LIMIT 1" in gaql

    assert report["currency"] == "GBP"
    assert report["truncated"] is True
    row = report["rows"][0]
    assert row["metrics.cost"] == 45.67
    assert row["metrics.cost_per_conversion"] == 5.7
    assert row["metrics.clicks"] == 120
    assert row["ad_group_criterion.criterion_id"] == "33"
    assert "campaign.resource_name" not in row


def test_unknown_metric_is_rejected_with_the_allowed_names(google):
    with pytest.raises(ValueError, match="Unknown metrics"):
        run(reporting.get_performance, {"metrics": ["roas"]}, READ_ONLY)
    assert google.requests == []


def test_query_caps_rows_and_keeps_resource_names(google):
    google.respond({"results": [{"campaign": {"resourceName": "customers/1/campaigns/2", "name": "A"}}]})
    result = run(accounts.query, {"query": "SELECT campaign.name FROM campaign LIMIT 5000"}, READ_ONLY)
    assert google.body()["query"] == "SELECT campaign.name FROM campaign LIMIT 50"
    assert result["rows"][0]["campaign.resource_name"] == "customers/1/campaigns/2"


def test_query_must_be_a_select(google):
    with pytest.raises(ValueError, match="SELECT"):
        run(accounts.query, {"query": "DELETE campaign"}, READ_ONLY)


def test_no_account_asks_the_agent_to_choose_one(google):
    with pytest.raises(ValueError, match="list_accounts"):
        run(campaigns.list_campaigns, {}, {"access": "read_only"})


def test_expired_access_is_refreshed_once_and_retried(google, monkeypatch):
    async def fake_refresh(refresh_token: str) -> dict:
        assert refresh_token == "refresh"
        return {"access_token": "fresh", "expires_in": 3600}

    monkeypatch.setattr("src.skills.google_ads.client.refresh_access_token", fake_refresh)
    google.respond({"error": {"code": 401, "status": "UNAUTHENTICATED"}}, status=401)
    google.respond({"results": []})

    run(campaigns.list_campaigns, {}, READ_ONLY)

    assert [request.headers["authorization"] for request in google.requests] == ["Bearer access", "Bearer fresh"]


def test_google_errors_become_short_actionable_messages(google):
    google.respond(
        {
            "error": {
                "code": 400,
                "status": "INVALID_ARGUMENT",
                "message": "Request contains an invalid argument.",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.ads.googleads.v25.errors.GoogleAdsFailure",
                        "errors": [
                            {
                                "errorCode": {"queryError": "UNRECOGNIZED_FIELD"},
                                "message": "Unrecognized field in the query: 'campaign.nme'.",
                                "location": {"fieldPathElements": [{"fieldName": "query"}]},
                            }
                        ],
                    }
                ],
            }
        },
        status=400,
    )
    with pytest.raises(GoogleAdsError) as error:
        run(accounts.query, {"query": "SELECT campaign.nme FROM campaign"}, READ_ONLY)
    assert str(error.value) == (
        "Google Ads API error 400 (INVALID_ARGUMENT): queryError=UNRECOGNIZED_FIELD at query - "
        "Unrecognized field in the query: 'campaign.nme'."
    )


def test_keyword_ideas_use_the_seed_and_flatten_metrics(google):
    google.respond(
        {"results": [{"text": "trail shoes", "keywordIdeaMetrics": {"avgMonthlySearches": "2400", "competition": "HIGH", "lowTopOfPageBidMicros": "1200000"}}]}
    )
    result = run(reporting.generate_keyword_ideas, {"keywords": ["running shoes"], "location_ids": [2826]}, READ_ONLY)
    body = google.body()
    assert google.requests[0].url.path == "/v25/customers/1234567890:generateKeywordIdeas"
    assert body["keywordSeed"] == {"keywords": ["running shoes"]}
    assert body["geoTargetConstants"] == ["geoTargetConstants/2826"]
    assert result["ideas"] == [{"text": "trail shoes", "avg_monthly_searches": 2400, "competition": "HIGH", "low_top_of_page_bid": 1.2}]


# --- write guards ------------------------------------------------------------------------------


def test_read_only_install_rejects_every_write_without_calling_google(google):
    with pytest.raises(ValueError, match="read-only"):
        run(campaigns.pause_campaigns, {"campaign_ids": ["11"]}, READ_ONLY)
    with pytest.raises(ValueError, match="read-only"):
        run(campaigns.pause_campaigns, {"campaign_ids": ["11"]}, READ_ONLY, AUTOMATION_CONTEXT)
    assert google.requests == []


def test_writes_need_a_budget_cap(google):
    with pytest.raises(ValueError, match="maximum daily budget"):
        run(campaigns.pause_campaigns, {"campaign_ids": ["11"]}, {"customer_id": CUSTOMER, "access": "read_write"})


def test_budgets_over_the_cap_are_rejected_everywhere(google):
    with pytest.raises(ValueError, match="exceeds this skill's cap of 50"):
        run(campaigns.update_budget, {"campaign_id": "11", "daily_budget": 80})
    with pytest.raises(ValueError, match="exceeds"):
        run(campaigns.create_search_campaign, {"name": "Big", "daily_budget": 51})
    with pytest.raises(ValueError, match="exceeds"):
        run(
            mutate.mutate,
            {"operations": [{"campaignBudgetOperation": {"update": {"resourceName": "customers/1/campaignBudgets/9", "amountMicros": "90000000"}, "updateMask": "amount_micros"}}]},
            {**READ_WRITE, "allow_advanced_mutate": "true"},
        )
    # Budget automations are capped too.
    with pytest.raises(ValueError, match="exceeds"):
        run(campaigns.update_budget, {"campaign_id": "11", "daily_budget": 80}, READ_WRITE, AUTOMATION_CONTEXT)
    assert google.requests == []


def test_raw_mutate_is_off_unless_allowed(google):
    with pytest.raises(ValueError, match="Raw mutate is turned off"):
        run(mutate.mutate, {"operations": [{"campaignOperation": {"remove": "customers/1/campaigns/2"}}]})


# --- preview then apply ------------------------------------------------------------------------


NEGATIVES = {"campaign_id": "11", "keywords": [{"text": "free", "match_type": "BROAD"}]}


def test_preview_validates_and_apply_needs_the_matching_token(google):
    preview = run(keywords.add_negative_keywords, NEGATIVES)

    assert preview["status"] == "preview"
    assert google.body()["validateOnly"] is True
    assert google.body()["mutateOperations"] == [
        {
            "campaignCriterionOperation": {
                "create": {
                    "campaign": "customers/1234567890/campaigns/11",
                    "negative": True,
                    "keyword": {"text": "free", "matchType": "BROAD"},
                }
            }
        }
    ]
    assert preview["summary"] == ["Add 1 negative keyword(s) to campaign 11", "-[BROAD] free"]

    with pytest.raises(ValueError, match="needs the confirmation_token"):
        run(keywords.add_negative_keywords, {**NEGATIVES, "mode": "apply"})
    tampered = {**NEGATIVES, "keywords": [{"text": "cheap", "match_type": "BROAD"}]}
    with pytest.raises(ValueError, match="differ from the previewed change"):
        run(keywords.add_negative_keywords, {**tampered, "mode": "apply", "confirmation_token": preview["confirmation_token"]})

    google.respond({"mutateOperationResponses": [{"campaignCriterionResult": {"resourceName": "customers/1234567890/campaignCriteria/11~99"}}]})
    applied = run(keywords.add_negative_keywords, {**NEGATIVES, "mode": "apply", "confirmation_token": preview["confirmation_token"]})

    assert google.body()["validateOnly"] is False
    assert applied == {
        "status": "applied",
        "customer_id": CUSTOMER,
        "summary": preview["summary"],
        "results": ["customers/1234567890/campaignCriteria/11~99"],
    }


def test_a_token_is_bound_to_the_installed_skill_and_expires(google, monkeypatch):
    preview = run(campaigns.pause_campaigns, {"campaign_ids": ["11"]})
    other_install = {**AGENT_CONTEXT, "installed_skill_id": "google_ads:other"}
    with pytest.raises(ValueError, match="differ"):
        run(campaigns.pause_campaigns, {"campaign_ids": ["11"], "mode": "apply", "confirmation_token": preview["confirmation_token"]}, READ_WRITE, other_install)

    later = datetime.now(timezone.utc) + timedelta(minutes=16)
    monkeypatch.setattr("src.skills.google_ads.confirmation.time.time", lambda: later.timestamp())
    with pytest.raises(ValueError, match="expired"):
        run(campaigns.pause_campaigns, {"campaign_ids": ["11"], "mode": "apply", "confirmation_token": preview["confirmation_token"]})


def test_automation_runs_apply_directly(google):
    result = run(campaigns.pause_campaigns, {"campaign_ids": "11"}, READ_WRITE, AUTOMATION_CONTEXT)
    assert result["status"] == "applied"
    assert len(google.requests) == 1
    assert google.body()["validateOnly"] is False
    assert google.body()["mutateOperations"] == [
        {"campaignOperation": {"update": {"resourceName": "customers/1234567890/campaigns/11", "status": "PAUSED"}, "updateMask": "status"}}
    ]


def test_create_search_campaign_is_one_atomic_paused_batch(google):
    result = run(
        campaigns.create_search_campaign,
        {
            "name": "Trail",
            "daily_budget": 20,
            "max_cpc": 1.5,
            "location_ids": [2826],
            "language_ids": [1000],
            "ad_groups": json.dumps(
                [
                    {
                        "name": "Trail shoes",
                        "keywords": [{"text": "trail running shoes", "match_type": "PHRASE"}],
                        "ads": [
                            {
                                "headlines": ["Trail Shoes", "Grip On Any Trail", "Free Delivery"],
                                "descriptions": ["Built for mud and rock.", "Order today."],
                                "final_url": "https://example.com/trail",
                            }
                        ],
                    }
                ]
            ),
        },
    )

    operations = google.body()["mutateOperations"]
    kinds = [next(iter(operation)) for operation in operations]
    assert kinds == [
        "campaignBudgetOperation",
        "campaignOperation",
        "campaignCriterionOperation",
        "campaignCriterionOperation",
        "adGroupOperation",
        "adGroupCriterionOperation",
        "adGroupAdOperation",
    ]
    budget = operations[0]["campaignBudgetOperation"]["create"]
    campaign = operations[1]["campaignOperation"]["create"]
    ad_group = operations[4]["adGroupOperation"]["create"]
    assert budget["resourceName"] == "customers/1234567890/campaignBudgets/-1"
    assert budget["amountMicros"] == "20000000"
    assert campaign["resourceName"] == "customers/1234567890/campaigns/-2"
    assert campaign["campaignBudget"] == budget["resourceName"]
    assert campaign["status"] == "PAUSED"
    assert campaign["targetSpend"] == {"cpcBidCeilingMicros": "1500000"}
    assert campaign["containsEuPoliticalAdvertising"] == "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING"
    assert ad_group["campaign"] == campaign["resourceName"]
    assert operations[5]["adGroupCriterionOperation"]["create"]["adGroup"] == ad_group["resourceName"]
    assert result["summary"][0] == "Create Search campaign 'Trail' (PAUSED)"


def test_update_budget_reads_the_current_budget_and_warns_when_shared(google):
    google.respond({"results": [{"campaign": {"name": "Shoes"}, "campaignBudget": {"resourceName": "customers/1234567890/campaignBudgets/7", "amountMicros": "10000000", "explicitlyShared": True}}]})
    preview = run(campaigns.update_budget, {"campaign_id": "11", "daily_budget": 25})
    assert preview["summary"] == [
        "Change the daily budget of campaign 'Shoes' from 10 to 25",
        "This budget is shared: every campaign that uses it changes too",
    ]
    assert google.body()["mutateOperations"] == [
        {"campaignBudgetOperation": {"update": {"resourceName": "customers/1234567890/campaignBudgets/7", "amountMicros": "25000000"}, "updateMask": "amount_micros"}}
    ]


def test_responsive_search_ad_limits_are_enforced_before_google(google):
    with pytest.raises(ValueError, match="3 to 15 headlines"):
        run(ads.create_responsive_search_ad, {"ad_group_id": "22", "headlines": ["A", "B"], "descriptions": ["x", "y"], "final_url": "https://e.com"})
    with pytest.raises(ValueError, match="30 characters"):
        run(ads.create_responsive_search_ad, {"ad_group_id": "22", "headlines": ["A" * 31, "B", "C"], "descriptions": ["x", "y"], "final_url": "https://e.com"})
    assert google.requests == []


def test_recommendations_preview_without_calling_google_then_apply(google):
    names = ["customers/1234567890/recommendations/abc"]
    preview = run(recommendations.apply_recommendations, {"resource_names": names})
    assert preview["status"] == "preview"
    assert google.requests == []

    run(recommendations.apply_recommendations, {"resource_names": names, "mode": "apply", "confirmation_token": preview["confirmation_token"]})
    assert google.requests[0].url.path == "/v25/customers/1234567890/recommendations:apply"
    assert google.body() == {"operations": [{"resourceName": names[0]}], "partialFailure": False}

    with pytest.raises(ValueError, match="not a recommendation of account"):
        run(recommendations.dismiss_recommendations, {"resource_names": ["customers/999/recommendations/x"]})


def test_blank_form_fields_mean_not_given(google):
    run(keywords.add_keywords, {"customer_id": "", "ad_group_id": "22", "keywords": '[{"text":"shoes","match_type":"EXACT"}]', "mode": "", "confirmation_token": ""})
    assert google.body()["validateOnly"] is True
    assert google.body()["mutateOperations"][0]["adGroupCriterionOperation"]["create"]["keyword"] == {"text": "shoes", "matchType": "EXACT"}


# --- manifest ----------------------------------------------------------------------------------


def test_every_action_is_available_to_automations_with_a_form():
    manifest = SkillRegistry().get("google_ads").manifest
    assert len(manifest.actions) == 29
    for action in manifest.actions:
        assert action.automation.enabled, action.name
        assert action.action_form is not None, action.name
        form_fields = {field.name for field in action.action_form.form_inputs}
        assert set(action.input_schema.get("required", [])) <= form_fields, action.name
        assert not {"mode", "confirmation_token"} & form_fields, action.name


def test_install_form_accepts_read_write_with_a_cap_and_rejects_unknown_access():
    registry = SkillRegistry()
    config = registry.validate_config("google_ads", {"customer_id": "123-456-7890", "access": "read_write", "max_daily_budget": "40"})
    assert config["access"] == "read_write"
    assert config["allow_advanced_mutate"] == "false"
    with pytest.raises(ValueError, match="Invalid value for access"):
        registry.validate_config("google_ads", {"access": "admin"})
