"""The social_media skill: list accounts, check a post, publish it to LinkedIn, and never post the same thing twice."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from src.config import settings
from src.config.settings import SocialAppCredentials
from src.connectors.social import networks
from src.connectors.social.models import SocialAccount, SocialAccountStatus
from src.connectors.social.networks.linkedin import LinkedInNetwork, escape_commentary
from src.connectors.social.repository import SocialAccountRepository
from src.crypto import encrypt
from src.skills.registry import get_skill_registry
from src.skills.social_media import actions
from tests.mock_data import TEST_USER_EMAIL, account_for, user_id_for

ACCOUNT_ID = account_for(TEST_USER_EMAIL)
POST_URN = "urn:li:share:7000000000000000001"


class FakeLinkedInPosts:
    def __init__(self) -> None:
        self.status = 201
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status == 201:
            return httpx.Response(201, headers={"x-restli-id": POST_URN})
        return httpx.Response(self.status, json={"message": "nope"})

    def bodies(self) -> list[dict]:
        return [json.loads(request.content) for request in self.requests]


@pytest.fixture
def linkedin(monkeypatch) -> FakeLinkedInPosts:
    fake = FakeLinkedInPosts()
    monkeypatch.setattr(networks, "NETWORKS", (LinkedInNetwork(transport=httpx.MockTransport(fake)),))
    monkeypatch.setattr(settings, "social_apps", {"linked_in": SocialAppCredentials("id", "secret")})
    return fake


def connect(handle: str = "Ada Lovelace", *, external_id: str = "member-1", expires_in: timedelta = timedelta(days=30)) -> SocialAccount:
    return SocialAccountRepository().connect(SocialAccount(
        account_id=ACCOUNT_ID, network="linkedin", external_id=external_id, handle=handle, display_name=handle,
        encrypted_credentials=encrypt(json.dumps({"access_token": "li-secret-token", "person_urn": f"urn:li:person:{external_id}"})),
        token_expires_at=datetime.now(timezone.utc) + expires_in, connected_by=user_id_for(TEST_USER_EMAIL),
    ))


def context(**extra) -> dict:
    return {"account_id": ACCOUNT_ID, **extra}


def automation_context(run: str = "run-1", node: str = "post") -> dict:
    return context(orchestrator_type="automation", automation_run_id=run, automation_node_id=node)


async def publish(text: str = "Hello LinkedIn", ctx: dict | None = None, **arguments) -> dict:
    return await actions.publish({"text": text, **arguments}, {}, ctx or context())


def test_the_skill_is_in_the_catalog_with_its_three_actions():
    manifest = get_skill_registry().get("social_media").manifest
    assert [action.name for action in manifest.actions] == ["accounts", "check", "publish"]
    assert manifest.owner_only


def test_linkedin_reserved_characters_are_escaped_so_the_post_is_not_cut_short():
    assert escape_commentary("Ship it (now) #win @team_a") == r"Ship it \(now\) \#win \@team\_a"


@pytest.mark.asyncio
async def test_accounts_lists_each_account_with_its_limit_and_no_credentials(dynamodb_table, linkedin):
    connect()
    result = await actions.accounts({}, {}, context())
    [account] = result["accounts"]
    assert account["network"] == "linkedin" and account["status"] == "active" and account["max_characters"] == 3000
    assert "li-secret-token" not in json.dumps(result)


@pytest.mark.asyncio
async def test_check_reports_a_text_that_is_too_long_and_an_expired_sign_in(dynamodb_table, linkedin):
    connect("Ada", external_id="a")
    connect("Grace", external_id="b", expires_in=timedelta(days=-1))
    result = await actions.check({"text": "x" * 3001}, {}, context())
    reasons = {target["handle"]: target["reason"] for target in result["targets"]}
    assert reasons == {"Ada": "text_too_long", "Grace": "needs_reconnect"}


@pytest.mark.asyncio
async def test_publish_posts_to_linkedin_and_returns_the_link(dynamodb_table, linkedin):
    connect()
    result = await publish("Launch (today)")
    assert result["status"] == "published"
    [target] = result["targets"]
    assert target["url"] == f"https://www.linkedin.com/feed/update/{POST_URN}"
    [body] = linkedin.bodies()
    assert body["author"] == "urn:li:person:member-1" and body["commentary"] == r"Launch \(today\)"
    assert linkedin.requests[0].headers["authorization"] == "Bearer li-secret-token"
    assert "li-secret-token" not in json.dumps(result)


@pytest.mark.asyncio
async def test_a_retried_automation_step_does_not_post_twice(dynamodb_table, linkedin):
    connect()
    first = await publish(ctx=automation_context())
    again = await publish(ctx=automation_context())
    assert len(linkedin.requests) == 1
    assert again["targets"] == first["targets"]


@pytest.mark.asyncio
async def test_two_automation_runs_each_post(dynamodb_table, linkedin):
    connect()
    await publish(ctx=automation_context("run-1"))
    await publish(ctx=automation_context("run-2"))
    assert len(linkedin.requests) == 2


@pytest.mark.asyncio
async def test_a_rejected_post_may_be_tried_again_by_the_retry(dynamodb_table, linkedin):
    connect()
    same_post = context(automation_run_id="r", automation_node_id="n")
    linkedin.status = 422
    failed = await publish(ctx=same_post)
    assert failed["status"] == "failed" and failed["targets"][0]["reason"] == "rejected"
    linkedin.status = 201
    retried = await publish(ctx=same_post)
    assert retried["status"] == "published"


@pytest.mark.asyncio
async def test_an_uncertain_post_is_never_sent_again(dynamodb_table, linkedin):
    connect()
    same_post = context(automation_run_id="r", automation_node_id="n")
    linkedin.status = 502
    first = await publish(ctx=same_post)
    linkedin.status = 201
    again = await publish(ctx=same_post)
    assert first["targets"][0]["status"] == again["targets"][0]["status"] == "uncertain"
    assert len(linkedin.requests) == 1


@pytest.mark.asyncio
async def test_a_refused_token_marks_the_account_as_needing_reconnect(dynamodb_table, linkedin):
    account = connect()
    linkedin.status = 401
    result = await publish()
    assert result["targets"][0]["reason"] == "auth"
    assert SocialAccountRepository().get(ACCOUNT_ID, account.social_account_id).status == SocialAccountStatus.NEEDS_RECONNECT


@pytest.mark.asyncio
async def test_an_automation_step_fails_when_nothing_was_posted(dynamodb_table, linkedin):
    connect()
    linkedin.status = 422
    with pytest.raises(RuntimeError, match="Nothing was posted"):
        await publish(ctx=automation_context())


@pytest.mark.asyncio
async def test_one_failed_account_does_not_stop_the_other(dynamodb_table, linkedin):
    connect("Ada", external_id="a")
    connect("Grace", external_id="b", expires_in=timedelta(days=-1))
    result = await publish()
    assert result["status"] == "partial"
    assert {target["handle"]: target["status"] for target in result["targets"]} == {"Ada": "published", "Grace": "skipped"}


@pytest.mark.asyncio
async def test_a_chosen_account_is_the_only_one_posted_to(dynamodb_table, linkedin):
    connect("Ada", external_id="a")
    grace = connect("Grace", external_id="b")
    await publish(accounts=[grace.social_account_id])
    assert [body["author"] for body in linkedin.bodies()] == ["urn:li:person:b"]


@pytest.mark.asyncio
async def test_publishing_with_nothing_connected_says_where_to_connect(dynamodb_table, linkedin):
    with pytest.raises(ValueError, match="Social tab"):
        await publish()


@pytest.mark.asyncio
async def test_an_unknown_network_or_account_is_an_error(dynamodb_table, linkedin):
    connect()
    with pytest.raises(ValueError, match="Unknown social network"):
        await publish(network="myspace")
    with pytest.raises(ValueError, match="No connected social account"):
        await publish(accounts=["nope"])
