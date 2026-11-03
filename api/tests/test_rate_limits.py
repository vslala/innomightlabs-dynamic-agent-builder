from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import status
from fastapi import HTTPException

from tests.mock_data import TEST_USER_EMAIL, kb_fields


@pytest.mark.parametrize("counter_value", [Decimal("7"), 7, None])
def test_usage_record_normalizes_dynamodb_counters(counter_value):
    from src.rate_limits.models import UsageRecord

    counters = ("messages_used", "kb_pages_used")
    item = {"user_email": TEST_USER_EMAIL, "period_key": "2026-11"}
    if counter_value is not None:
        item.update(dict.fromkeys(counters, counter_value))

    usage = UsageRecord.from_dynamo_item(item)

    for counter in counters:
        value = getattr(usage, counter)
        assert type(value) is int
        assert value == (0 if counter_value is None else 7)


@pytest.mark.parametrize(
    ("path", "counter"),
    [
        ("/agents/test-agent/test-conversation/send-message", "messages_used"),
        ("/knowledge-bases/test-kb/crawl-jobs", "kb_pages_used"),
    ],
)
def test_quota_response_serializes_dynamodb_usage(
    test_client, auth_headers, dynamodb_table, monkeypatch, path, counter
):
    from src.config import settings
    from src.payments.pricing_config import PricingTierLimits
    from src.rate_limits.service import RateLimitService

    monkeypatch.setattr(settings, "superuser_emails", [])
    monkeypatch.setattr(RateLimitService, "get_user_tier", lambda self, email: "free")
    monkeypatch.setattr(
        RateLimitService,
        "get_tier_limits",
        lambda self, tier: PricingTierLimits(
            agents=1, messages_per_month=1, kb_pages=1, memory_blocks=1,
        ),
    )
    period_key = datetime.now(timezone.utc).strftime("%Y-%m")
    usage_key = {"pk": f"User#{TEST_USER_EMAIL}", "sk": f"Usage#{period_key}"}
    dynamodb_table.put_item(Item={
        **usage_key,
        "user_email": TEST_USER_EMAIL,
        "period_key": period_key,
        counter: Decimal("1"),
    })
    assert isinstance(dynamodb_table.get_item(Key=usage_key)["Item"][counter], Decimal)
    items_before = dynamodb_table.scan()["Items"]

    response = test_client.post(
        path,
        json={"agent_name": "Quota Rejected Agent", "max_pages": 1, **_agent_payload()},
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    detail = response.json()["detail"]
    assert detail["current"] == 1
    assert type(detail["current"]) is int
    assert detail["limit"] == 1
    assert detail["tier"] == "free"
    assert "upgrade_url" in detail
    if counter == "kb_pages_used":
        assert detail["remaining"] == 0
        assert type(detail["remaining"]) is int
    # Quota rejection must not reach the route or create an agent (or other resource).
    assert dynamodb_table.scan()["Items"] == items_before


def test_quota_middleware_encodes_exception_detail_and_preserves_headers(
    test_client, auth_headers, dynamodb_table, monkeypatch
):
    from src.rate_limits.service import RateLimitService

    def reject_agent(self, billed_email, quota, requested=1):
        raise HTTPException(
            status_code=429,
            detail={"current": Decimal("2"), "nested": {"remaining": Decimal("0")}},
            headers={"Retry-After": "60", "X-Quota-Limit": "agents"},
        )

    monkeypatch.setattr(RateLimitService, "check", reject_agent)
    items_before = dynamodb_table.scan()["Items"]

    response = test_client.post(
        "/agents",
        json={"agent_name": "Rejected Agent", **_agent_payload()},
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.json() == {"detail": {"current": 2, "nested": {"remaining": 0}}}
    assert response.headers["Retry-After"] == "60"
    assert response.headers["X-Quota-Limit"] == "agents"
    assert dynamodb_table.scan()["Items"] == items_before


def _create_kb(kb_repo, name: str = "Test KB"):
    from src.knowledge.models import KnowledgeBase

    kb = KnowledgeBase(
        name=name,
        description="Test knowledge base",
        **kb_fields(TEST_USER_EMAIL),
    )
    return kb_repo.save(kb)


def test_crawl_job_rejects_when_over_limit(test_client, auth_headers, dynamodb_table):
    from src.knowledge.repository import KnowledgeBaseRepository

    kb_repo = KnowledgeBaseRepository()
    kb = _create_kb(kb_repo)

    payload = {
        "source_type": "sitemap",
        "source_url": "https://example.com/sitemap.xml",
        "max_pages": 20,
    }

    response = test_client.post(
        f"/knowledge-bases/{kb.kb_id}/crawl-jobs?auto_start=true",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    data = response.json()
    assert "upgrade_url" in data["detail"]


def test_crawl_job_defaults_to_max_pages_limit(test_client, auth_headers, dynamodb_table):
    from src.knowledge.repository import KnowledgeBaseRepository

    kb_repo = KnowledgeBaseRepository()
    kb = _create_kb(kb_repo, name="Default Limit KB")

    payload = {
        "source_type": "sitemap",
        "source_url": "https://example.com/sitemap.xml",
    }

    response = test_client.post(
        f"/knowledge-bases/{kb.kb_id}/crawl-jobs?auto_start=true",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_crawl_job_creation_allows_when_not_auto_started(test_client, auth_headers, dynamodb_table):
    from src.knowledge.repository import KnowledgeBaseRepository

    kb_repo = KnowledgeBaseRepository()
    kb = _create_kb(kb_repo, name="Manual KB")

    payload = {
        "source_type": "sitemap",
        "source_url": "https://example.com/sitemap.xml",
        "max_pages": 999,
    }

    response = test_client.post(
        f"/knowledge-bases/{kb.kb_id}/crawl-jobs?auto_start=false",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_201_CREATED


def test_agent_limit_respects_latest_paid_plan(test_client, auth_headers, dynamodb_table):
    from src.payments.subscriptions import Subscription, SubscriptionRepository

    repo = SubscriptionRepository()
    repo.upsert(
        Subscription(
            subscription_id="sub-free",
            user_email=TEST_USER_EMAIL,
            status="active",
            plan_name="free",
        )
    )
    repo.upsert(
        Subscription(
            subscription_id="sub-business",
            user_email=TEST_USER_EMAIL,
            status="active",
            plan_name="business",
        )
    )

    response1 = test_client.post("/agents", json={"agent_name": "Agent One", **_agent_payload()}, headers=auth_headers)
    response2 = test_client.post("/agents", json={"agent_name": "Agent Two", **_agent_payload()}, headers=auth_headers)

    assert response1.status_code == status.HTTP_201_CREATED
    assert response2.status_code == status.HTTP_201_CREATED


def _agent_payload():
    return {
        "agent_architecture": "krishna-memgpt",
        "agent_provider": "Bedrock",
        "agent_model": "claude-3-sonnet",
        "agent_persona": "Test persona",
    }


def _service_at_its_limits(monkeypatch, superusers: list[str]):
    """A service whose free plan allows one of everything, with one of everything already used."""
    from src.config import settings
    from src.payments.pricing_config import PricingTierLimits
    from src.rate_limits.models import UsageRecord
    from src.rate_limits.service import RateLimitService

    service = RateLimitService()
    monkeypatch.setattr(settings, "superuser_emails", superusers)
    monkeypatch.setattr(service, "get_tier_limits", lambda _tier: PricingTierLimits(
        agents=1, messages_per_month=1, kb_pages=1, memory_blocks=1,
    ))
    monkeypatch.setattr(service, "get_user_tier", lambda _email: "free")
    monkeypatch.setattr(service, "_agents_charged_to", lambda _email: [object()])
    monkeypatch.setattr(service.usage_repo, "get_usage", lambda _email, period: UsageRecord(
        user_email=TEST_USER_EMAIL, period_key=period, messages_used=1, kb_pages_used=1,
    ))
    return service


QUOTA_REQUESTS = [("agents", 1), ("messages", 1), ("kb_pages", 10)]


@pytest.mark.parametrize(("quota_name", "requested"), QUOTA_REQUESTS)
def test_superuser_bypasses_all_rate_limit_checks(dynamodb_table, monkeypatch, quota_name, requested):
    from src.rate_limits import quotas

    service = _service_at_its_limits(monkeypatch, [TEST_USER_EMAIL.lower()])

    service.check(TEST_USER_EMAIL, getattr(quotas, quota_name.upper()), requested)


@pytest.mark.parametrize(("quota_name", "requested"), QUOTA_REQUESTS)
def test_non_superuser_still_gets_rate_limit_errors(dynamodb_table, monkeypatch, quota_name, requested):
    from src.rate_limits import quotas

    service = _service_at_its_limits(monkeypatch, [])

    with pytest.raises(HTTPException) as refused:
        service.check(TEST_USER_EMAIL, getattr(quotas, quota_name.upper()), requested)

    assert refused.value.status_code == 429
    assert refused.value.detail["remaining"] == 0


def test_a_request_that_fits_what_is_left_is_allowed(dynamodb_table, monkeypatch):
    from src.payments.pricing_config import PricingTierLimits
    from src.rate_limits.quotas import KB_PAGES

    service = _service_at_its_limits(monkeypatch, [])  # one page used
    monkeypatch.setattr(service, "get_tier_limits", lambda _tier: PricingTierLimits(
        agents=1, messages_per_month=1, kb_pages=5, memory_blocks=1,
    ))

    service.check(TEST_USER_EMAIL, KB_PAGES, 4)
    with pytest.raises(HTTPException):
        service.check(TEST_USER_EMAIL, KB_PAGES, 5)


@pytest.mark.parametrize(("method", "path", "quota_name"), [
    ("POST", "/agents", "agents"),
    ("POST", "/agents/a1/c1/send-message", "messages"),
    ("POST", "/builder/s1/send-message", "messages"),
    ("POST", "/knowledge-bases/kb1/crawl-jobs", "kb_pages"),
    ("POST", "/knowledge-bases/kb1/crawl-jobs/j1/run", "kb_pages"),
    ("POST", "/knowledge-bases/kb1/crawl-jobs/j1/run-stream", "kb_pages"),
    ("GET", "/agents", None),
    ("POST", "/agents/a1", None),
    ("POST", "/agents/a1/c1/send-message/extra", None),
    ("POST", "/knowledge-bases/kb1/crawl-jobs/j1", None),
])
def test_each_limited_route_selects_its_quota(method, path, quota_name):
    from starlette.requests import Request
    from src.rate_limits.middleware import rule_for

    selected = rule_for(Request({"type": "http", "method": method, "path": path, "headers": [], "query_string": b""}))

    assert (selected[0].quota.name if selected else None) == quota_name


def test_a_limited_route_with_a_broken_body_is_refused(test_client, auth_headers):
    response = test_client.post(
        "/agents", content=b"{not json", headers={**auth_headers, "Content-Type": "application/json"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"]["message"] == "Invalid JSON payload."


def test_recreating_an_agent_by_name_is_not_counted_again(test_client, auth_headers, monkeypatch):
    from src.config import settings
    from src.payments.pricing_config import PricingTierLimits
    from src.rate_limits.service import RateLimitService

    monkeypatch.setattr(settings, "superuser_emails", [])
    monkeypatch.setattr(RateLimitService, "get_user_tier", lambda self, email: "free")
    monkeypatch.setattr(RateLimitService, "get_tier_limits", lambda self, tier: PricingTierLimits(
        agents=1, messages_per_month=1, kb_pages=1, memory_blocks=1,
    ))
    body = {"agent_name": "Only One", **_agent_payload()}

    first = test_client.post("/agents", json=body, headers=auth_headers)
    again = test_client.post("/agents", json=body, headers=auth_headers)
    another = test_client.post("/agents", json={**body, "agent_name": "Second"}, headers=auth_headers)

    assert first.status_code == status.HTTP_201_CREATED
    assert again.status_code != status.HTTP_429_TOO_MANY_REQUESTS
    assert another.status_code == status.HTTP_429_TOO_MANY_REQUESTS
