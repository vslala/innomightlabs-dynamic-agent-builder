"""Limits are the account owner's: a member's agents, messages and crawled pages are charged to the plan of the
owner of the account they act in, not to the member's own plan."""

from datetime import datetime, timezone

import pytest
from fastapi import status

from src.accounts import AccountService, Member
from src.config import settings
from src.iam.service import IamService
from src.identity import IdentityRepository
from src.payments.pricing_config import PricingTierLimits
from src.rate_limits.billing import account_billing_email
from src.rate_limits.models import UsageRecord
from src.rate_limits.repository import UsageRepository
from src.rate_limits.service import RateLimitService
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, set_up_bedrock, user_id_for
from tests.oauth_handoff import owner_headers

OWNER, MEMBER = user_id_for(TEST_USER_EMAIL), user_id_for(TEST_USER_EMAIL_2)
AGENT = {
    "agent_architecture": "krishna-memgpt", "agent_provider": "Bedrock",
    "agent_model": "claude-3-sonnet", "agent_persona": "Test persona",
}
# The owner's plan has room (3 of everything); the member's own plan would stop at 1
PLANS = {"free": PricingTierLimits(agents=1, messages_per_month=1, kb_pages=1, memory_blocks=1),
         "team": PricingTierLimits(agents=3, messages_per_month=3, kb_pages=3, memory_blocks=1)}


@pytest.fixture
def team(dynamodb_table, monkeypatch) -> str:
    """An account the owner pays for (team plan) with a member whose own plan is free."""
    created = AccountService().create_account(IdentityRepository().get(OWNER), "Team").account_id
    identity = IdentityRepository().get(MEMBER)
    dynamodb_table.put_item(Item=Member(
        account_id=created, user_id=MEMBER, email=identity.email, name=identity.name, invited_by=OWNER,
    ).to_dynamo_item())
    IamService().attach(created, OWNER, "member", MEMBER, "MemberAccess")
    set_up_bedrock(created)

    monkeypatch.setattr(settings, "superuser_emails", [])
    tiers = {TEST_USER_EMAIL: "team"}
    monkeypatch.setattr(RateLimitService, "get_user_tier", lambda self, email: tiers.get(email, "free"))
    monkeypatch.setattr(RateLimitService, "get_tier_limits", lambda self, tier: PLANS[tier])
    return created


def in_account(email: str, account_id: str | None = None) -> dict[str, str]:
    return {**owner_headers(email), **({"X-Account-Id": account_id} if account_id else {})}


def create_agent(test_client, name: str, headers: dict[str, str]):
    return test_client.post("/agents", json={"agent_name": name, **AGENT}, headers=headers)


def used(email: str, **counters: int) -> None:
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    UsageRepository().table.put_item(Item=UsageRecord(user_email=email, period_key=period, **counters).to_dynamo_item())


def test_a_member_creates_agents_against_the_owners_plan(test_client, team):
    member = in_account(TEST_USER_EMAIL_2, team)

    created = [create_agent(test_client, f"Agent {n}", member).status_code for n in range(3)]
    refused = create_agent(test_client, "Agent 4", member)

    assert created == [status.HTTP_201_CREATED] * 3, "the member's free plan would have stopped at one"
    assert refused.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert refused.json()["detail"]["tier"] == "team"
    assert (refused.json()["detail"]["limit"], refused.json()["detail"]["current"]) == (3, 3)


def test_everyones_agents_in_the_account_count_together(test_client, team):
    create_agent(test_client, "Owner one", in_account(TEST_USER_EMAIL, team))
    create_agent(test_client, "Owner two", in_account(TEST_USER_EMAIL, team))
    create_agent(test_client, "Member one", in_account(TEST_USER_EMAIL_2, team))

    by_member = create_agent(test_client, "Member two", in_account(TEST_USER_EMAIL_2, team))
    by_owner = create_agent(test_client, "Owner three", in_account(TEST_USER_EMAIL, team))

    assert by_member.status_code == by_owner.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_a_members_own_account_is_charged_to_them(test_client, team):
    create_agent(test_client, "Shared", in_account(TEST_USER_EMAIL_2, team))

    first = create_agent(test_client, "Mine", in_account(TEST_USER_EMAIL_2))
    second = create_agent(test_client, "Mine too", in_account(TEST_USER_EMAIL_2))

    assert first.status_code == status.HTTP_201_CREATED, "an agent in the shared account isn't theirs to pay for"
    assert second.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert second.json()["detail"]["tier"] == "free"


def test_a_superuser_owner_exempts_the_whole_account(test_client, team, monkeypatch):
    member = in_account(TEST_USER_EMAIL_2, team)
    for n in range(3):
        create_agent(test_client, f"Agent {n}", member)
    assert create_agent(test_client, "Over the limit", member).status_code == status.HTTP_429_TOO_MANY_REQUESTS

    monkeypatch.setattr(settings, "superuser_emails", [TEST_USER_EMAIL.lower()])

    assert create_agent(test_client, "Over the limit", member).status_code == status.HTTP_201_CREATED


def test_messages_are_charged_to_the_owners_plan(test_client, team):
    send = "/agents/some-agent/some-conversation/send-message"
    used(TEST_USER_EMAIL_2, messages_used=5)  # the member's own quota is long spent

    allowed = test_client.post(send, json={"content": "Hi"}, headers=in_account(TEST_USER_EMAIL_2, team))
    used(TEST_USER_EMAIL, messages_used=3)
    refused = test_client.post(send, json={"content": "Hi"}, headers=in_account(TEST_USER_EMAIL_2, team))

    assert allowed.status_code != status.HTTP_429_TOO_MANY_REQUESTS
    assert refused.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert refused.json()["detail"]["tier"] == "team"


def test_crawled_pages_are_charged_to_the_owners_plan(test_client, team):
    crawl = "/knowledge-bases/some-kb/crawl-jobs"
    body = {"source_type": "sitemap", "source_url": "https://example.com/sitemap.xml", "max_pages": 3}
    used(TEST_USER_EMAIL_2, kb_pages_used=9)

    allowed = test_client.post(crawl, json=body, headers=in_account(TEST_USER_EMAIL_2, team))
    used(TEST_USER_EMAIL, kb_pages_used=2)
    refused = test_client.post(crawl, json=body, headers=in_account(TEST_USER_EMAIL_2, team))

    assert allowed.status_code != status.HTTP_429_TOO_MANY_REQUESTS
    assert refused.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert refused.json()["detail"]["remaining"] == 1


def test_an_account_the_caller_is_not_in_is_refused_by_the_route_not_limited(test_client, team):
    stranger = AccountService().create_account(IdentityRepository().get(user_id_for("owner@example.com")), "Not mine")

    response = create_agent(test_client, "Intruder", in_account(TEST_USER_EMAIL_2, stranger.account_id))

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"]["code"] == "NOT_A_MEMBER"


def test_the_billed_email_is_the_account_owners(team):
    assert account_billing_email(team) == TEST_USER_EMAIL
    assert account_billing_email("no-such-account") is None
