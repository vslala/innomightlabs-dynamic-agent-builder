"""Kits and Ila's sessions in shared accounts (KAN-80): a blueprint builds in the account the request acts in, a kit
is private until shared, admins see metadata only, nothing crosses accounts, and a building session is the
member's alone."""
import pytest
from fastapi.testclient import TestClient

from src.accounts import AccountService, Member
from src.agents.repository import AgentRepository
from src.blueprints.catalog import example_yaml
from src.blueprints.kinds import knowledge_base as knowledge_base_kind
from src.config import settings
from src.iam.service import IamService
from src.identity import IdentityRepository
from src.knowledge.service import KnowledgeBaseService
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, user_id_for
from tests.oauth_handoff import owner_headers

ADMIN_EMAIL, ALICE_EMAIL, BOB_EMAIL = TEST_USER_EMAIL, TEST_USER_EMAIL_2, "someone-else@example.com"
OUTSIDER_EMAIL = "owner@example.com"
ALICE, BOB = user_id_for(ALICE_EMAIL), user_id_for(BOB_EMAIL)
SITE_AGENT = example_yaml("site-agent") or ""
PARAMS = {"site_url": "https://acme.example", "business_name": "Acme"}


@pytest.fixture
def account(dynamodb_table, monkeypatch) -> str:
    """Owned by ADMIN; Alice and Bob are members with MemberAccess, as after accepting invites."""
    monkeypatch.setattr(knowledge_base_kind, "launch_crawl", lambda job_id, *_: None)
    monkeypatch.setattr(settings, "require_pinecone", lambda: None)
    monkeypatch.setattr(KnowledgeBaseService, "_delete_pinecone_namespace", lambda self, kb_id: 0)
    created = AccountService().create_account(IdentityRepository().get(user_id_for(ADMIN_EMAIL)), "Team")
    for email in (ALICE_EMAIL, BOB_EMAIL):
        identity = IdentityRepository().find_by_email(email)
        dynamodb_table.put_item(Item=Member(account_id=created.account_id, user_id=identity.user_id,
                                            email=email, name=identity.name).to_dynamo_item())
        IamService().attach(created.account_id, user_id_for(ADMIN_EMAIL), "member", identity.user_id, "MemberAccess")
        ProviderSettingsRepository().save(
            ProviderSettings(user_email=email, provider_name="Bedrock", encrypted_credentials="{}")
        )
    return created.account_id


def as_(email: str, account: str) -> dict[str, str]:
    return {**owner_headers(email), "X-Account-Id": account}


@pytest.fixture
def alices_kit(account, test_client: TestClient) -> dict:
    response = test_client.post("/blueprints/deployments", json={"yaml": SITE_AGENT, "params": PARAMS},
                                headers=as_(ALICE_EMAIL, account))
    assert response.status_code == 201, response.text
    return response.json()


def listed(test_client: TestClient, email: str, account: str) -> dict[str, str]:
    return {kit["kit_id"]: kit["access"] for kit in test_client.get("/kits", headers=as_(email, account)).json()}


def test_a_blueprint_builds_in_the_account_the_request_acts_in(test_client, account, alices_kit):
    assert (alices_kit["account_id"], alices_kit["owner_id"]) == (account, ALICE)
    agent = AgentRepository().find_in_account(account, alices_kit["resources"]["assistant"]["id"])
    assert agent is not None and agent.owner_id == ALICE
    assert listed(test_client, ALICE_EMAIL, account)[alices_kit["kit_id"]] == "owner"
    assert test_client.get("/kits", headers=owner_headers(ALICE_EMAIL)).json() == [], "not in her personal account"


def test_a_kit_is_private_until_shared_and_a_viewer_only_looks(test_client, account, alices_kit):
    kit_id, bob = alices_kit["kit_id"], as_(BOB_EMAIL, account)
    assert kit_id not in listed(test_client, BOB_EMAIL, account)
    assert test_client.get(f"/kits/{kit_id}", headers=bob).status_code == 404

    shared = test_client.put(f"/kits/{kit_id}/shares/members/{BOB}", headers=as_(ALICE_EMAIL, account),
                             json={"preset": "viewer"})

    assert shared.status_code == 200, shared.text
    assert listed(test_client, BOB_EMAIL, account)[kit_id] == "shared"
    assert test_client.get(f"/kits/{kit_id}", headers=bob).status_code == 200
    assert test_client.post(f"/kits/{kit_id}/removal/plan", headers=bob).status_code == 403
    assert test_client.post(f"/kits/{kit_id}/rollback/plan", headers=bob, json={"version": 1}).status_code == 403
    applied = test_client.post("/blueprints/deployments", headers=bob,
                               json={"yaml": SITE_AGENT, "params": PARAMS, "kit_id": kit_id})
    assert applied.status_code == 403


def test_admins_see_and_remove_but_not_open_it(test_client, account, alices_kit):
    kit_id, admin = alices_kit["kit_id"], as_(ADMIN_EMAIL, account)

    assert listed(test_client, ADMIN_EMAIL, account)[kit_id] == "admin"
    assert test_client.get(f"/kits/{kit_id}", headers=admin).status_code == 403
    plan = test_client.post(f"/kits/{kit_id}/removal/plan", headers=admin)
    assert plan.status_code == 200, plan.text
    removed = test_client.post(f"/kits/{kit_id}/remove", headers=admin, json={"plan_id": plan.json()["plan_id"]})
    assert removed.status_code == 200, removed.text
    assert AgentRepository().find_in_account(account, alices_kit["resources"]["assistant"]["id"]) is None, \
        "it removes as the kit's owner"


def test_nothing_reaches_across_accounts(test_client, account, alices_kit):
    kit_id = alices_kit["kit_id"]
    assert test_client.get(f"/kits/{kit_id}", headers=owner_headers(OUTSIDER_EMAIL)).status_code == 404
    assert test_client.get(f"/kits/{kit_id}", headers=as_(OUTSIDER_EMAIL, account)).status_code == 403
    deployment = alices_kit["deployment_id"]
    assert test_client.get(f"/blueprints/deployments/{deployment}", headers=owner_headers(ALICE_EMAIL)).status_code == 404
    assert test_client.get(f"/blueprints/deployments/{deployment}", headers=as_(BOB_EMAIL, account)).status_code == 404


def test_a_building_session_is_the_members_own_in_its_account(test_client, account):
    alice = as_(ALICE_EMAIL, account)
    created = test_client.post("/builder/sessions", headers=alice, json={"agent_provider": "Bedrock"})
    assert created.status_code == 201, created.text
    conversation_id = created.json()["conversation_id"]

    assert conversation_id in {s["conversation_id"] for s in test_client.get("/builder/sessions", headers=alice).json()}
    for other in (as_(BOB_EMAIL, account), owner_headers(ALICE_EMAIL)):
        assert conversation_id not in {s["conversation_id"] for s in
                                       test_client.get("/builder/sessions", headers=other).json()}
        assert test_client.get(f"/builder/{conversation_id}/turns/active", headers=other).status_code == 404
