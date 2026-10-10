"""Automations and schedules in shared accounts (KAN-80): private by default, shared on purpose, admins see
metadata only, nothing crosses accounts, and an automation runs as its owner whoever starts it."""
import pytest
from fastapi.testclient import TestClient

from src.accounts import AccountService, Member
from src.iam.service import IamService
from src.iam.shares import ShareRepository
from src.identity import IdentityRepository
from tests.mock_data import AUTOMATION_CREATE_REQUEST, TEST_USER_EMAIL, TEST_USER_EMAIL_2, user_id_for
from tests.oauth_handoff import owner_headers

ADMIN_EMAIL, ALICE_EMAIL, BOB_EMAIL = TEST_USER_EMAIL, TEST_USER_EMAIL_2, "someone-else@example.com"
OUTSIDER_EMAIL = "owner@example.com"
ALICE, BOB = user_id_for(ALICE_EMAIL), user_id_for(BOB_EMAIL)


@pytest.fixture
def account(dynamodb_table) -> str:
    """Owned by ADMIN; Alice and Bob are members with MemberAccess, as after accepting invites."""
    created = AccountService().create_account(IdentityRepository().get(user_id_for(ADMIN_EMAIL)), "Team")
    for email in (ALICE_EMAIL, BOB_EMAIL):
        identity = IdentityRepository().find_by_email(email)
        dynamodb_table.put_item(Item=Member(account_id=created.account_id, user_id=identity.user_id,
                                            email=email, name=identity.name).to_dynamo_item())
        IamService().attach(created.account_id, user_id_for(ADMIN_EMAIL), "member", identity.user_id, "MemberAccess")
    return created.account_id


def as_(email: str, account: str) -> dict[str, str]:
    return {**owner_headers(email), "X-Account-Id": account}


@pytest.fixture
def alices_automation(account, test_client: TestClient) -> str:
    response = test_client.post("/automations", json=AUTOMATION_CREATE_REQUEST, headers=as_(ALICE_EMAIL, account))
    assert response.status_code == 201, response.text
    return response.json()["automation"]["automation_id"]


def share(test_client: TestClient, account: str, automation_id: str, user_id: str, preset: str) -> None:
    response = test_client.put(f"/automations/{automation_id}/shares/members/{user_id}",
                               headers=as_(ALICE_EMAIL, account), json={"preset": preset})
    assert response.status_code == 200, response.text


def listed(test_client: TestClient, email: str, account: str) -> dict[str, str]:
    return {a["automation_id"]: a["access"] for a in test_client.get("/automations", headers=as_(email, account)).json()}


def test_an_automation_is_created_in_the_account_the_request_acts_in(test_client, account, alices_automation):
    automation = test_client.get(f"/automations/{alices_automation}", headers=as_(ALICE_EMAIL, account)).json()

    assert (automation["account_id"], automation["owner_id"], automation["access"]) == (account, ALICE, "owner")
    personal = test_client.get("/automations", headers=owner_headers(ALICE_EMAIL)).json()
    assert alices_automation not in {a["automation_id"] for a in personal}


def test_other_members_cannot_see_it_until_it_is_shared(test_client, account, alices_automation):
    bob = as_(BOB_EMAIL, account)
    assert alices_automation not in listed(test_client, BOB_EMAIL, account)
    assert test_client.get(f"/automations/{alices_automation}/graph", headers=bob).status_code == 404

    share(test_client, account, alices_automation, BOB, "viewer")

    assert listed(test_client, BOB_EMAIL, account)[alices_automation] == "shared"
    assert test_client.get(f"/automations/{alices_automation}/graph", headers=bob).status_code == 200
    assert test_client.patch(f"/automations/{alices_automation}", headers=bob, json={"title": "Mine"}).status_code == 403
    assert test_client.post(f"/automations/{alices_automation}/test-run", headers=bob, json={"input": {}}).status_code == 403
    assert test_client.delete(f"/automations/{alices_automation}", headers=bob).status_code == 403


def test_a_shared_automation_runs_as_its_owner_whoever_starts_it(test_client, account, alices_automation, monkeypatch):
    started = {}
    monkeypatch.setattr("src.automations.router.invoke_automation_run_async",
                        lambda run_id, automation_id, owner: started.update(owner=owner))
    share(test_client, account, alices_automation, BOB, "user")

    response = test_client.post(f"/automations/{alices_automation}/test-run", headers=as_(BOB_EMAIL, account),
                                json={"input": {}})

    assert response.status_code == 202, response.text
    assert (started["owner"].user_id, started["owner"].email) == (ALICE, ALICE_EMAIL)
    assert response.json()["created_by"] == ALICE


def test_admins_see_and_delete_but_not_open_it(test_client, account, alices_automation):
    admin = as_(ADMIN_EMAIL, account)

    assert listed(test_client, ADMIN_EMAIL, account)[alices_automation] == "admin"
    assert test_client.get(f"/automations/{alices_automation}", headers=admin).json()["access"] == "admin"
    assert test_client.get(f"/automations/{alices_automation}/graph", headers=admin).status_code == 403
    assert test_client.get(f"/automations/{alices_automation}/runs", headers=admin).status_code == 403
    assert test_client.delete(f"/automations/{alices_automation}", headers=admin).status_code == 204


def test_nothing_reaches_across_accounts(test_client, account, alices_automation):
    assert test_client.get(f"/automations/{alices_automation}", headers=owner_headers(OUTSIDER_EMAIL)).status_code == 404
    assert test_client.get(f"/automations/{alices_automation}", headers=as_(OUTSIDER_EMAIL, account)).status_code == 403


def test_deleting_an_automation_forgets_its_shares(test_client, account, alices_automation):
    share(test_client, account, alices_automation, BOB, "viewer")

    test_client.delete(f"/automations/{alices_automation}", headers=as_(ALICE_EMAIL, account))

    assert ShareRepository().on_resource(account, "automation", alices_automation) == []


def test_schedules_are_each_members_own(test_client, account):
    body = {"name": "Daily", "cron_expression": "0 9 * * *", "target_type": "automation_run",
            "target": {"automation_id": "a-1"}}
    created = test_client.post("/schedules", json=body, headers=as_(ALICE_EMAIL, account))
    assert created.status_code == 201, created.text
    schedule = created.json()
    assert (schedule["account_id"], schedule["owner_id"]) == (account, ALICE)

    bob = as_(BOB_EMAIL, account)
    assert schedule["schedule_id"] not in {s["schedule_id"] for s in test_client.get("/schedules", headers=bob).json()}
    assert test_client.get(f"/schedules/{schedule['schedule_id']}", headers=bob).status_code == 404
    assert test_client.get(f"/schedules/{schedule['schedule_id']}", headers=owner_headers(ALICE_EMAIL)).status_code == 404, \
        "it stays in the account it was made in"
