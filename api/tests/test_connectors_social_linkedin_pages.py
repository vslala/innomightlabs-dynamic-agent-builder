"""LinkedIn Pages: one sign-in connects every page the member can post as, and a post is by the page."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from src.config import settings
from src.config.settings import SocialAppCredentials
from src.connectors.social import networks
from src.connectors.social.networks.linkedin import LinkedInNetwork
from src.connectors.social.networks.linkedin_pages import LinkedInPagesNetwork
from src.connectors.social.repository import SocialAccountRepository
from tests.mock_data import TEST_USER_EMAIL, account_for
from tests.oauth_handoff import handoff_result, owner_headers

RETURN_TO = "http://localhost:5173/dashboard/connectors?tab=social"
REDIRECT = "http://localhost:8000/connectors/social/oauth/callback"


class FakeLinkedIn:
    """LinkedIn's token, page-roles, page-details, posts and revoke endpoints."""

    def __init__(self) -> None:
        self.roles = [("111", "ADMINISTRATOR"), ("222", "CONTENT_ADMIN"), ("333", "ANALYST")]
        self.names = {"111": ("Acme", "acme"), "222": ("Acme Labs", None)}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/accessToken"):
            return httpx.Response(200, json={"access_token": "page-token", "expires_in": 5184000, "scope": "r_organization_admin,w_organization_social"})
        if path == "/rest/organizationAcls":
            return httpx.Response(200, json={"elements": [
                {"organization": f"urn:li:organization:{page}", "role": role, "state": "APPROVED"} for page, role in self.roles]})
        if path.startswith("/rest/organizations/"):
            name = self.names.get(path.rsplit("/", 1)[1])
            if name is None:
                return httpx.Response(404, json={})
            return httpx.Response(200, json={"localizedName": name[0], **({"vanityName": name[1]} if name[1] else {})})
        if path == "/rest/posts":
            return httpx.Response(201, headers={"x-restli-id": "urn:li:share:9"})
        return httpx.Response(200)

    def calls(self, path: str) -> list[httpx.Request]:
        return [request for request in self.requests if request.url.path.endswith(path)]


@pytest.fixture
def linkedin(monkeypatch) -> FakeLinkedIn:
    fake = FakeLinkedIn()
    transport = httpx.MockTransport(fake)
    monkeypatch.setattr(networks, "NETWORKS", (LinkedInNetwork(transport=transport), LinkedInPagesNetwork(transport=transport)))
    monkeypatch.setattr(settings, "social_apps", {
        "linked_in": SocialAppCredentials("profile-id", "profile-secret"),
        "linked_in_pages": SocialAppCredentials("pages-id", "pages-secret"),
    })
    monkeypatch.setattr(settings, "social_oauth_redirect_uri", REDIRECT)
    return fake


def connect_pages(test_client) -> dict[str, list[str]]:
    start = test_client.post("/connectors/social/networks/linkedin_page/connect", json={"return_to": RETURN_TO},
                             headers=owner_headers())
    state = parse_qs(urlparse(start.json()["authorize_url"]).query)["state"][0]
    callback = test_client.get("/connectors/social/oauth/callback", params={"code": "auth-code", "state": state},
                               follow_redirects=False)
    return handoff_result(test_client, callback, TEST_USER_EMAIL)


def accounts(test_client) -> list[dict]:
    return test_client.get("/connectors/social/accounts", headers=owner_headers()).json()


def test_the_pages_network_is_offered_beside_the_profile_network_with_a_description(test_client, linkedin):
    offered = test_client.get("/connectors/social/networks", headers=owner_headers()).json()
    assert {network["key"]: network["description"] for network in offered} == {
        "linkedin": "Post as yourself, to your personal profile.",
        "linkedin_page": "Post as a company page you administer.",
    }


def test_the_pages_sign_in_asks_for_the_page_scopes_with_its_own_app(test_client, linkedin):
    start = test_client.post("/connectors/social/networks/linkedin_page/connect", json={"return_to": RETURN_TO},
                             headers=owner_headers())
    query = parse_qs(urlparse(start.json()["authorize_url"]).query)
    assert query["client_id"] == ["pages-id"]
    assert query["scope"] == ["r_organization_admin w_organization_social"]


def test_one_sign_in_connects_every_page_the_member_can_post_as(test_client, linkedin):
    result = connect_pages(test_client)

    assert result["social_oauth"] == ["success"] and len(result["social_account_ids"][0].split(",")) == 2
    shown = {account["display_name"]: account for account in accounts(test_client)}
    assert set(shown) == {"Acme", "Acme Labs"}, "an analyst role can't post, so that page is left out"
    assert shown["Acme"]["network"] == "linkedin_page"
    saved = {account.external_id: account for account in SocialAccountRepository().list(account_for(TEST_USER_EMAIL))}
    assert saved["111"].handle == "@acme" and saved["222"].handle == "Acme Labs"
    assert saved["111"].credentials()["author_urn"] == "urn:li:organization:111"
    assert "page-token" not in json.dumps(accounts(test_client))


def test_a_member_with_no_pages_is_told_so(test_client, linkedin):
    linkedin.roles = [("333", "ANALYST")]
    result = connect_pages(test_client)
    assert result["social_oauth"] == ["error"] and result["reason"] == ["callback_failed"]
    assert accounts(test_client) == []


def test_a_page_whose_details_cannot_be_read_is_still_connected(test_client, linkedin):
    linkedin.names = {}
    connect_pages(test_client)
    assert sorted(account["display_name"] for account in accounts(test_client)) == ["LinkedIn page 111", "LinkedIn page 222"]


@pytest.mark.asyncio
async def test_a_post_is_authored_and_its_images_owned_by_the_page(dynamodb_table, linkedin):
    from src.connectors.social.networks.base import PreparedPost

    network = LinkedInPagesNetwork(transport=httpx.MockTransport(linkedin))
    published = await network.publish(
        {"access_token": "page-token", "author_urn": "urn:li:organization:111"}, PreparedPost(text="Hello"))
    assert json.loads(linkedin.calls("/rest/posts")[0].content)["author"] == "urn:li:organization:111"
    assert published.url == "https://www.linkedin.com/feed/update/urn:li:share:9"


def test_disconnecting_one_page_keeps_the_grant_the_others_use_until_the_last_goes(test_client, linkedin):
    connect_pages(test_client)
    first, second = accounts(test_client)

    test_client.delete(f"/connectors/social/accounts/{first['social_account_id']}", headers=owner_headers())
    assert linkedin.calls("/revoke") == []

    test_client.delete(f"/connectors/social/accounts/{second['social_account_id']}", headers=owner_headers())
    assert len(linkedin.calls("/revoke")) == 1
