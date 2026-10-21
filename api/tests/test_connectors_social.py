"""Social connectors: connect a LinkedIn account through the shared OAuth handoff, see it, reconnect it, remove it."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from src.accounts import AccountService, Member
from src.config import settings
from src.config.settings import SocialAppCredentials, social_apps_from_env
from src.connectors.social import networks
from src.connectors.social.connect import SocialOAuthState, decode_state
from src.connectors.social.models import SocialAccountStatus, external_key
from src.connectors.social.networks.linkedin import LinkedInNetwork
from src.connectors.social.repository import SocialAccountRepository
from src.crypto import encrypt
from src.iam.service import IamService
from src.identity import IdentityRepository
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, account_for, user_id_for
from tests.oauth_handoff import handoff_result, owner_headers

RETURN_TO = "http://localhost:5173/dashboard/connectors?tab=social"
REDIRECT = "http://localhost:8000/connectors/social/oauth/callback"
MEMBER_EMAIL = TEST_USER_EMAIL_2


class FakeLinkedIn:
    """LinkedIn's three endpoints, recording what they were asked."""

    def __init__(self, *, sub: str = "member-1", name: str = "Ada Lovelace", expires_in: int | None = 5184000):
        self.sub, self.name, self.expires_in = sub, name, expires_in
        self.token_status = 200
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/accessToken"):
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "invalid_request"})
            body = {"access_token": "li-access-token", "scope": "openid,profile,w_member_social"}
            if self.expires_in is not None:
                body["expires_in"] = self.expires_in
            return httpx.Response(200, json=body)
        if request.url.path.endswith("/userinfo"):
            return httpx.Response(200, json={"sub": self.sub, "name": self.name, "picture": "https://media.example/ada.jpg"})
        return httpx.Response(200)

    def posted(self, path: str) -> dict[str, list[str]]:
        request = next(request for request in self.requests if request.url.path.endswith(path))
        return parse_qs(request.content.decode())


@pytest.fixture
def linkedin(monkeypatch) -> FakeLinkedIn:
    fake = FakeLinkedIn()
    monkeypatch.setattr(networks, "NETWORKS", (LinkedInNetwork(transport=httpx.MockTransport(fake)),))
    monkeypatch.setattr(settings, "social_apps", {"linked_in": SocialAppCredentials("client-id", "client-secret")})
    monkeypatch.setattr(settings, "social_oauth_redirect_uri", REDIRECT)
    return fake


@pytest.fixture
def team(dynamodb_table) -> str:
    """Owned by the test user, who is an admin; another seeded person is a plain member."""
    created = AccountService().create_account(IdentityRepository().get(user_id_for(TEST_USER_EMAIL)), "Team")
    identity = IdentityRepository().find_by_email(MEMBER_EMAIL)
    dynamodb_table.put_item(Item=Member(account_id=created.account_id, user_id=identity.user_id,
                                        email=MEMBER_EMAIL, name=identity.name).to_dynamo_item())
    IamService().attach(created.account_id, user_id_for(TEST_USER_EMAIL), "member", identity.user_id, "MemberAccess")
    return created.account_id


def as_(email: str, account: str | None = None) -> dict[str, str]:
    return {**owner_headers(email), **({"X-Account-Id": account} if account else {})}


def start(test_client, email: str = TEST_USER_EMAIL, account: str | None = None, return_to: str = RETURN_TO):
    return test_client.post("/connectors/social/networks/linkedin/connect", json={"return_to": return_to},
                            headers=as_(email, account))


def state_of(authorize_url: str) -> str:
    return parse_qs(urlparse(authorize_url).query)["state"][0]


def connect(test_client, email: str = TEST_USER_EMAIL, account: str | None = None) -> dict[str, list[str]]:
    """Sign in to LinkedIn end to end: start, the provider's redirect to our callback, then the SPA's completion."""
    authorize_url = start(test_client, email, account).json()["authorize_url"]
    callback = test_client.get("/connectors/social/oauth/callback",
                               params={"code": "auth-code", "state": state_of(authorize_url)}, follow_redirects=False)
    return handoff_result(test_client, callback, email)


def accounts(test_client, email: str = TEST_USER_EMAIL, account: str | None = None) -> list[dict]:
    response = test_client.get("/connectors/social/accounts", headers=as_(email, account))
    assert response.status_code == 200, response.text
    return response.json()


# --- Settings -----------------------------------------------------------------------------------------------------


def test_oauth_apps_are_read_from_pairs_of_env_vars_named_after_the_network():
    apps = social_apps_from_env({
        "SOCIAL_LINKED_IN_CLIENT_ID": " id-1 ",
        "SOCIAL_LINKED_IN_CLIENT_SECRET": "secret-1",
        "SOCIAL_X_CLIENT_ID": "id-2",
        "SOCIAL_BLUESKY_CLIENT_ID": "",
        "SOCIAL_OAUTH_REDIRECT_URI": "https://api.example/callback",
        "GOOGLE_CLIENT_ID": "not-social",
    })

    assert apps == {
        "linked_in": SocialAppCredentials("id-1", "secret-1"),
        "x": SocialAppCredentials("id-2", ""),
    }


# --- The networks offered -----------------------------------------------------------------------------------------


def test_a_network_is_offered_only_once_its_oauth_app_is_registered(test_client, linkedin, monkeypatch):
    offered = test_client.get("/connectors/social/networks", headers=owner_headers()).json()
    assert offered == [{"key": "linkedin", "display_name": "LinkedIn", "icon": "linkedin"}]

    monkeypatch.setattr(settings, "social_apps", {})

    assert test_client.get("/connectors/social/networks", headers=owner_headers()).json() == []
    assert start(test_client).status_code == 400


# --- Connecting ---------------------------------------------------------------------------------------------------


def test_the_sign_in_link_asks_linkedin_for_what_posting_needs(test_client, linkedin):
    response = start(test_client)

    assert response.status_code == 200, response.text
    url = urlparse(response.json()["authorize_url"])
    query = parse_qs(url.query)
    assert f"{url.scheme}://{url.netloc}{url.path}" == "https://www.linkedin.com/oauth/v2/authorization"
    assert query["client_id"] == ["client-id"]
    assert query["redirect_uri"] == [REDIRECT]
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["openid profile w_member_social"]
    session = decode_state(query["state"][0])
    assert session and session.network == "linkedin" and session.return_to == RETURN_TO


def test_connecting_saves_the_members_account_and_hides_its_credentials(test_client, linkedin, dynamodb_table):
    result = connect(test_client)

    assert result["social_oauth"] == ["success"] and result["network"] == ["linkedin"]
    (shown,) = accounts(test_client)
    assert (shown["network"], shown["display_name"], shown["status"]) == ("linkedin", "Ada Lovelace", "active")
    assert shown["avatar_url"] == "https://media.example/ada.jpg"
    assert "access_token" not in json.dumps(shown) and "encrypted_credentials" not in shown

    exchange = linkedin.posted("/accessToken")
    assert exchange["code"] == ["auth-code"] and exchange["client_secret"] == ["client-secret"]
    assert exchange["redirect_uri"] == [REDIRECT]

    saved = SocialAccountRepository().list(account_for(TEST_USER_EMAIL))[0]
    assert "li-access-token" not in saved.encrypted_credentials, "stored encrypted"
    assert saved.token_expires_at and saved.token_expires_at > datetime.now(timezone.utc) + timedelta(days=59)


def test_connecting_the_same_member_again_refreshes_the_account_instead_of_duplicating_it(test_client, linkedin):
    connect(test_client)
    first = accounts(test_client)[0]
    repository = SocialAccountRepository()
    stale = repository.list(account_for(TEST_USER_EMAIL))[0].model_copy(
        update={"status": SocialAccountStatus.NEEDS_RECONNECT, "last_error": "token revoked"})
    repository.table.put_item(Item=stale.to_dynamo_item())
    assert accounts(test_client)[0]["status"] == "needs_reconnect"

    linkedin.name = "Ada King"
    connect(test_client)

    (again,) = accounts(test_client)
    assert again["social_account_id"] == first["social_account_id"]
    assert (again["status"], again["display_name"], again["last_error"]) == ("active", "Ada King", None)


def test_the_log_says_whether_linkedin_sent_a_refresh_token_without_leaking_tokens(test_client, linkedin, caplog):
    with caplog.at_level("INFO", logger="src.connectors.social.networks.linkedin"):
        connect(test_client)

    assert "refresh_token=False expires_in=5184000" in caplog.text
    assert "li-access-token" not in caplog.text


def test_two_members_of_linkedin_are_two_accounts(test_client, linkedin):
    connect(test_client)
    linkedin.sub, linkedin.name = "member-2", "Grace Hopper"
    connect(test_client)

    assert [account["display_name"] for account in accounts(test_client)] == ["Ada Lovelace", "Grace Hopper"]


def test_a_token_that_has_run_out_needs_reconnecting(test_client, linkedin):
    connect(test_client)
    repository = SocialAccountRepository()
    expired = repository.list(account_for(TEST_USER_EMAIL))[0].model_copy(
        update={"token_expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)})
    repository.table.put_item(Item=expired.to_dynamo_item())

    assert accounts(test_client)[0]["status"] == "needs_reconnect"


def test_a_token_with_no_stated_lifetime_is_treated_as_lasting_sixty_days(test_client, linkedin):
    linkedin.expires_in = None
    connect(test_client)

    expires = SocialAccountRepository().list(account_for(TEST_USER_EMAIL))[0].token_expires_at
    assert expires and timedelta(days=59) < expires - datetime.now(timezone.utc) <= timedelta(days=60)


# --- Who may, and what is refused --------------------------------------------------------------------------------


def test_only_admins_connect_and_every_member_sees_the_accounts(test_client, linkedin, team):
    assert start(test_client, MEMBER_EMAIL, team).status_code == 403

    result = connect(test_client, TEST_USER_EMAIL, team)

    assert result["social_oauth"] == ["success"]
    assert [account["display_name"] for account in accounts(test_client, MEMBER_EMAIL, team)] == ["Ada Lovelace"]
    assert accounts(test_client, MEMBER_EMAIL) == [], "nor across accounts"
    (shown,) = accounts(test_client, TEST_USER_EMAIL, team)
    assert test_client.delete(f"/connectors/social/accounts/{shown['social_account_id']}",
                              headers=as_(MEMBER_EMAIL, team)).status_code == 403


def test_someone_else_completing_a_sign_in_saves_nothing(test_client, linkedin):
    authorize_url = start(test_client, TEST_USER_EMAIL).json()["authorize_url"]
    callback = test_client.get("/connectors/social/oauth/callback",
                               params={"code": "c", "state": state_of(authorize_url)}, follow_redirects=False)

    result = handoff_result(test_client, callback, MEMBER_EMAIL)

    assert result["reason"] == ["invalid_state"]
    assert accounts(test_client, TEST_USER_EMAIL) == [] and accounts(test_client, MEMBER_EMAIL) == []
    assert not [r for r in linkedin.requests if r.url.path.endswith("/accessToken")], "the code was never exchanged"


def test_the_callback_itself_saves_and_exchanges_nothing(test_client, linkedin):
    authorize_url = start(test_client).json()["authorize_url"]

    callback = test_client.get("/connectors/social/oauth/callback",
                               params={"code": "c", "state": state_of(authorize_url)}, follow_redirects=False)

    assert callback.status_code == 307
    assert callback.headers["location"].startswith(RETURN_TO + "&oauth_complete=")
    assert linkedin.requests == [] and accounts(test_client) == []


def test_an_expired_sign_in_is_refused(test_client, linkedin):
    session = SocialOAuthState(
        nonce="n", network="linkedin", account_id=account_for(TEST_USER_EMAIL), user_id=user_id_for(TEST_USER_EMAIL),
        user_email=TEST_USER_EMAIL, code_verifier="v", return_to=RETURN_TO,
        expires_at=int(datetime.now(timezone.utc).timestamp()) - 1,
    )
    callback = test_client.get("/connectors/social/oauth/callback",
                               params={"code": "c", "state": encrypt(session.model_dump_json())}, follow_redirects=False)

    assert handoff_result(test_client, callback)["reason"] == ["invalid_state"]
    assert accounts(test_client) == []


def test_a_sign_in_only_returns_to_this_app(test_client, linkedin):
    assert start(test_client, return_to="https://evil.example/steal").status_code == 400


def test_cancelling_at_linkedin_saves_nothing(test_client, linkedin):
    authorize_url = start(test_client).json()["authorize_url"]
    callback = test_client.get("/connectors/social/oauth/callback",
                               params={"error": "user_cancelled_authorize", "state": state_of(authorize_url)},
                               follow_redirects=False)

    result = handoff_result(test_client, callback)

    assert (result["social_oauth"], result["reason"]) == (["error"], ["cancelled"])
    assert accounts(test_client) == []


def test_a_code_linkedin_rejects_saves_nothing(test_client, linkedin):
    linkedin.token_status = 400

    result = connect(test_client)

    assert (result["social_oauth"], result["reason"], result["network"]) == (["error"], ["callback_failed"], ["linkedin"])
    assert accounts(test_client) == []


# --- Disconnecting ------------------------------------------------------------------------------------------------


def test_disconnecting_revokes_the_grant_and_forgets_the_account(test_client, linkedin, dynamodb_table):
    connect(test_client)
    (shown,) = accounts(test_client)

    response = test_client.delete(f"/connectors/social/accounts/{shown['social_account_id']}", headers=owner_headers())

    assert response.status_code == 204
    assert accounts(test_client) == []
    assert linkedin.posted("/revoke")["token"] == ["li-access-token"]
    guard = dynamodb_table.get_item(Key=external_key(account_for(TEST_USER_EMAIL), "linkedin", "member-1"))
    assert "Item" not in guard, "the same member can be connected again"
    assert connect(test_client)["social_oauth"] == ["success"]


def test_disconnecting_works_when_linkedin_cannot_be_reached(test_client, linkedin, monkeypatch):
    connect(test_client)
    (shown,) = accounts(test_client)

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(networks, "NETWORKS", (LinkedInNetwork(transport=httpx.MockTransport(unreachable)),))

    assert test_client.delete(f"/connectors/social/accounts/{shown['social_account_id']}",
                              headers=owner_headers()).status_code == 204
    assert accounts(test_client) == []


def test_disconnecting_an_account_that_is_not_there_is_a_404(test_client, linkedin):
    assert test_client.delete("/connectors/social/accounts/nope", headers=owner_headers()).status_code == 404
