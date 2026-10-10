"""The account a request acts in: X-Account-Id, else the last one used, else the oldest (KAN-79)."""
import pytest
from fastapi.testclient import TestClient

from src.accounts import AccountService, Member
from src.identity import IdentityRepository
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, user_id_for
from tests.oauth_handoff import owner_headers

ME, OTHER = user_id_for(TEST_USER_EMAIL), user_id_for(TEST_USER_EMAIL_2)


@pytest.fixture
def two_accounts(dynamodb_table) -> tuple[str, str]:
    """I own one account and am a member of another person's."""
    mine = AccountService().create_account(IdentityRepository().get(ME), "Mine").account_id
    theirs = AccountService().create_account(IdentityRepository().get(OTHER), "Theirs").account_id
    me = IdentityRepository().get(ME)
    dynamodb_table.put_item(Item=Member(account_id=theirs, user_id=ME, email=me.email, name=me.name,
                                        invited_by=OTHER).to_dynamo_item())
    return mine, theirs


def active(test_client: TestClient, headers: dict[str, str]) -> list[str]:
    return [a["name"] for a in test_client.get("/accounts", headers=headers).json() if a["active"]]


def test_requests_act_in_the_oldest_account_until_another_is_chosen(test_client, two_accounts):
    mine, theirs = two_accounts
    headers = owner_headers(TEST_USER_EMAIL)
    assert active(test_client, headers) == ["Mine"]

    switched = test_client.put("/accounts/active", headers=headers, json={"account_id": theirs})

    assert switched.status_code == 200 and switched.json()["name"] == "Theirs"
    assert active(test_client, headers) == ["Theirs"], "remembered on the identity, so on every device"
    assert IdentityRepository().get(ME).last_account_id == theirs


def test_the_header_names_the_account_for_one_request(test_client, two_accounts):
    mine, theirs = two_accounts
    test_client.put("/accounts/active", headers=owner_headers(TEST_USER_EMAIL), json={"account_id": theirs})

    assert active(test_client, {**owner_headers(TEST_USER_EMAIL), "X-Account-Id": mine}) == ["Mine"]


def test_a_forged_header_gets_nothing(test_client, two_accounts):
    stranger = AccountService().create_account(IdentityRepository().get(user_id_for("owner@example.com")), "Not mine")

    response = test_client.get("/iam/actions", headers={**owner_headers(TEST_USER_EMAIL),
                                                        "X-Account-Id": stranger.account_id})
    switched = test_client.put("/accounts/active", headers=owner_headers(TEST_USER_EMAIL),
                               json={"account_id": stranger.account_id})

    assert (response.status_code, response.json()["detail"]["code"]) == (403, "NOT_A_MEMBER")
    assert switched.status_code == 403
    assert IdentityRepository().get(ME).last_account_id is None


def test_a_suspended_membership_loses_access_at_once(test_client, two_accounts, dynamodb_table):
    mine, theirs = two_accounts
    headers = {**owner_headers(TEST_USER_EMAIL), "X-Account-Id": theirs}
    assert test_client.get("/iam/actions", headers=headers).status_code == 200

    dynamodb_table.update_item(Key={"pk": f"Account#{theirs}", "sk": f"Member#{ME}"},
                               UpdateExpression="SET #s = :s", ExpressionAttributeNames={"#s": "status"},
                               ExpressionAttributeValues={":s": "suspended"})

    assert test_client.get("/iam/actions", headers=headers).status_code == 403


def test_an_account_left_since_is_skipped(test_client, two_accounts, dynamodb_table):
    mine, theirs = two_accounts
    test_client.put("/accounts/active", headers=owner_headers(TEST_USER_EMAIL), json={"account_id": theirs})

    dynamodb_table.delete_item(Key={"pk": f"Account#{theirs}", "sk": f"Member#{ME}"})

    assert active(test_client, owner_headers(TEST_USER_EMAIL)) == ["Mine"]
    assert test_client.get("/iam/actions", headers=owner_headers(TEST_USER_EMAIL)).status_code == 200
