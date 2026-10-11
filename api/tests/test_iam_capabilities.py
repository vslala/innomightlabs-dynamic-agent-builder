"""Account-scoped IAM capabilities use effective permissions, not membership roles."""

import pytest

from src.accounts import AccountService, Member, personal_account_id
from src.iam.policy import VERSION
from src.iam.service import IamService
from src.identity import IdentityRepository
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, user_id_for
from tests.oauth_handoff import owner_headers

OWNER = user_id_for(TEST_USER_EMAIL)
MEMBER = user_id_for(TEST_USER_EMAIL_2)


@pytest.fixture
def account(dynamodb_table) -> str:
    created = AccountService().create_account(IdentityRepository().get(OWNER), "Team")
    identity = IdentityRepository().get(MEMBER)
    dynamodb_table.put_item(Item=Member(
        account_id=created.account_id, user_id=MEMBER, email=identity.email,
        name=identity.name, invited_by=OWNER,
    ).to_dynamo_item())
    IamService().attach(created.account_id, OWNER, "member", MEMBER, "MemberAccess")
    return created.account_id


def headers(email: str, account_id: str) -> dict[str, str]:
    return {**owner_headers(email), "X-Account-Id": account_id}


def test_owner_has_both_capabilities(test_client, account):
    response = test_client.get("/iam/capabilities", headers=headers(TEST_USER_EMAIL, account))

    assert response.status_code == 200, response.text
    assert response.json() == {"can_list_members": True, "can_invite": True}


def test_plain_member_can_list_but_not_invite(test_client, account):
    response = test_client.get("/iam/capabilities", headers=headers(TEST_USER_EMAIL_2, account))

    assert response.status_code == 200, response.text
    assert response.json() == {"can_list_members": True, "can_invite": False}


@pytest.mark.parametrize("action, expected", [
    (None, {"can_list_members": False, "can_invite": False}),
    ("iam:Invite", {"can_list_members": False, "can_invite": True}),
    ("iam:ListMembers", {"can_list_members": True, "can_invite": False}),
])
def test_capabilities_are_independently_delegated(test_client, account, action, expected):
    iam = IamService()
    iam.detach(account, OWNER, "member", MEMBER, "MemberAccess")
    if action is not None:
        policy = iam.create_policy(account, OWNER, "Delegated", {
            "Version": VERSION,
            "Statement": [{"Effect": "Allow", "Action": action, "Resource": "*"}],
        })
        iam.attach(account, OWNER, "member", MEMBER, policy.ref)

    response = test_client.get("/iam/capabilities", headers=headers(TEST_USER_EMAIL_2, account))

    assert response.status_code == 200, response.text
    assert response.json() == expected


@pytest.mark.parametrize("action, expected", [
    ("iam:Invite", {"can_list_members": True, "can_invite": False}),
    ("iam:ListMembers", {"can_list_members": False, "can_invite": True}),
])
def test_explicit_deny_overrides_allow_and_invalidates_cache(test_client, account, action, expected):
    iam = IamService()
    iam.attach(account, OWNER, "member", MEMBER, "AdministratorAccess")
    member_headers = headers(TEST_USER_EMAIL_2, account)
    before = test_client.get("/iam/capabilities", headers=member_headers)
    assert before.status_code == 200, before.text
    assert before.json() == {"can_list_members": True, "can_invite": True}
    policy = iam.create_policy(account, OWNER, "Restriction", {
        "Version": VERSION,
        "Statement": [{"Effect": "Deny", "Action": action, "Resource": "*"}],
    })
    iam.attach(account, OWNER, "member", MEMBER, policy.ref)

    response = test_client.get("/iam/capabilities", headers=member_headers)

    assert response.status_code == 200, response.text
    assert response.json() == expected


@pytest.mark.parametrize("target", ["missing-account", "owners-personal-account"])
def test_nonmember_cannot_select_another_account(test_client, account, target):
    account_id = personal_account_id(OWNER) if target == "owners-personal-account" else target
    response = test_client.get("/iam/capabilities", headers=headers(TEST_USER_EMAIL_2, account_id))

    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "NOT_A_MEMBER"


def test_delegated_permissions_do_not_leak_across_accounts(test_client, account):
    iam = IamService()
    policy = iam.create_policy(account, OWNER, "No invitations", {
        "Version": VERSION,
        "Statement": [{"Effect": "Deny", "Action": "iam:Invite", "Resource": "*"}],
    })
    iam.attach(account, OWNER, "member", MEMBER, policy.ref)
    personal = test_client.get("/iam/capabilities", headers=owner_headers(TEST_USER_EMAIL_2))
    shared = test_client.get("/iam/capabilities", headers=headers(TEST_USER_EMAIL_2, account))

    assert personal.status_code == shared.status_code == 200
    assert personal.json() == {"can_list_members": True, "can_invite": True}
    assert shared.json() == {"can_list_members": True, "can_invite": False}


def test_suspended_member_is_rejected_even_with_cached_permissions(test_client, account, dynamodb_table):
    member_headers = headers(TEST_USER_EMAIL_2, account)
    assert test_client.get("/iam/capabilities", headers=member_headers).status_code == 200
    dynamodb_table.update_item(
        Key={"pk": f"Account#{account}", "sk": f"Member#{MEMBER}"},
        UpdateExpression="SET #s = :s", ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "suspended"},
    )

    response = test_client.get("/iam/capabilities", headers=member_headers)

    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "NOT_A_MEMBER"


def test_anonymous_request_is_rejected(test_client):
    response = test_client.get("/iam/capabilities")

    assert response.status_code == 401, response.text
