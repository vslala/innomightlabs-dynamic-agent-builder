"""/leads: admins run the account's forms and see its leads; members only list forms; nothing crosses accounts."""

import pytest

from src.accounts import AccountService, Member
from src.iam.service import IamService
from src.identity import IdentityRepository
from src.leads.service import CaptureOrigin, LeadsService
from src.skills.models import ActorKind
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, user_id_for
from tests.oauth_handoff import owner_headers

ADMIN_EMAIL, MEMBER_EMAIL = TEST_USER_EMAIL, TEST_USER_EMAIL_2
DEMO_FORM = {
    "slug": "demo-request",
    "name": "Demo request",
    "form_inputs": [
        {"input_type": "text", "name": "name", "label": "Full name"},
        {"input_type": "text", "name": "email", "label": "Work email", "validation": {"format": "email"}},
    ],
}


@pytest.fixture
def account(dynamodb_table) -> str:
    """Owned by the admin; the member has MemberAccess, as after accepting an invite."""
    created = AccountService().create_account(IdentityRepository().get(user_id_for(ADMIN_EMAIL)), "Team")
    identity = IdentityRepository().find_by_email(MEMBER_EMAIL)
    dynamodb_table.put_item(Item=Member(account_id=created.account_id, user_id=identity.user_id,
                                        email=MEMBER_EMAIL, name=identity.name).to_dynamo_item())
    IamService().attach(created.account_id, user_id_for(ADMIN_EMAIL), "member", identity.user_id, "MemberAccess")
    return created.account_id


def as_(email: str, account: str) -> dict[str, str]:
    return {**owner_headers(email), "X-Account-Id": account}


def capture_jane(account: str) -> str:
    origin = CaptureOrigin(account_id=account, agent_id="agent-1", actor_kind=ActorKind.VISITOR, actor_id="visitor-1")
    return LeadsService().capture("demo-request", {"name": "Jane", "email": "jane@acme.com"}, origin).capture.capture_id


def test_admins_manage_forms_and_members_only_list_them(test_client, account):
    refused = test_client.post("/leads/forms", json=DEMO_FORM, headers=as_(MEMBER_EMAIL, account))
    assert refused.status_code == 403

    created = test_client.post("/leads/forms", json=DEMO_FORM, headers=as_(ADMIN_EMAIL, account))
    assert created.status_code == 201, created.text

    listed = test_client.get("/leads/forms", headers=as_(MEMBER_EMAIL, account))
    assert [form["slug"] for form in listed.json()] == ["demo-request"]
    assert test_client.get("/leads/settings", headers=as_(MEMBER_EMAIL, account)).status_code == 200


def test_only_admins_see_leads(test_client, account):
    test_client.post("/leads/forms", json=DEMO_FORM, headers=as_(ADMIN_EMAIL, account))
    capture_id = capture_jane(account)

    assert test_client.get("/leads/captures", headers=as_(MEMBER_EMAIL, account)).status_code == 403
    assert test_client.get(f"/leads/captures/{capture_id}", headers=as_(MEMBER_EMAIL, account)).status_code == 403

    page = test_client.get("/leads/captures", headers=as_(ADMIN_EMAIL, account)).json()
    assert [capture["answers"]["email"] for capture in page["items"]] == ["jane@acme.com"]
    updated = test_client.patch(f"/leads/captures/{capture_id}", json={"status": "contacted"},
                                headers=as_(ADMIN_EMAIL, account))
    assert updated.json()["status"] == "contacted"


def test_another_accounts_admin_sees_nothing(test_client, account):
    test_client.post("/leads/forms", json=DEMO_FORM, headers=as_(ADMIN_EMAIL, account))
    capture_id = capture_jane(account)

    # The member is the admin of their own personal account
    elsewhere = owner_headers(MEMBER_EMAIL)
    assert test_client.get("/leads/captures", headers=elsewhere).json()["items"] == []
    assert test_client.get(f"/leads/captures/{capture_id}", headers=elsewhere).status_code == 404
    assert test_client.get("/leads/forms", headers=elsewhere).json() == []


def test_refusals_carry_a_code_and_a_message(test_client, account):
    test_client.post("/leads/forms", json=DEMO_FORM, headers=as_(ADMIN_EMAIL, account))

    second = test_client.post("/leads/forms", json={**DEMO_FORM, "slug": "support"}, headers=as_(ADMIN_EMAIL, account))

    assert second.status_code == 429, "the free plan has one active form"
    assert second.json()["detail"]["code"] == "PLAN_LIMIT"
    assert "Upgrade" in second.json()["detail"]["message"]


def test_usage_reports_the_plan(test_client, account):
    test_client.post("/leads/forms", json=DEMO_FORM, headers=as_(ADMIN_EMAIL, account))
    capture_jane(account)

    usage = test_client.get("/leads/usage", headers=as_(ADMIN_EMAIL, account)).json()

    assert (usage["forms"], usage["forms_limit"], usage["captures"], usage["captures_limit"]) == (1, 1, 1, 25)
