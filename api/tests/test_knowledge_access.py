"""Knowledge bases in shared accounts (KAN-80): private by default, shared on purpose, admins see metadata
only, nothing crosses accounts, and an agent searches a knowledge base only while its owner may read it."""
import pytest
from fastapi.testclient import TestClient

from src.accounts import AccountService, Member
from src.agents.repository import AgentRepository
from src.iam.service import IamService
from src.iam.shares import ShareRepository
from src.identity import IdentityRepository
from src.knowledge.access import readable_by_agent
from tests.mock_data import AGENT_CREATE_REQUEST, TEST_USER_EMAIL, TEST_USER_EMAIL_2, user_id_for
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
def alices_kb(account, test_client: TestClient) -> str:
    response = test_client.post("/knowledge-bases", json={"name": "Alice's docs"}, headers=as_(ALICE_EMAIL, account))
    assert response.status_code == 201, response.text
    return response.json()["kb_id"]


def share(test_client: TestClient, account: str, kb_id: str, user_id: str, preset: str = "viewer") -> None:
    response = test_client.put(f"/knowledge-bases/{kb_id}/shares/members/{user_id}",
                               headers=as_(ALICE_EMAIL, account), json={"preset": preset})
    assert response.status_code == 200, response.text


def listed(test_client: TestClient, email: str, account: str) -> dict[str, str]:
    return {kb["kb_id"]: kb["access"] for kb in test_client.get("/knowledge-bases", headers=as_(email, account)).json()}


def test_a_knowledge_base_is_created_in_the_account_the_request_acts_in(test_client, account, alices_kb):
    kb = test_client.get(f"/knowledge-bases/{alices_kb}", headers=as_(ALICE_EMAIL, account)).json()

    assert (kb["account_id"], kb["owner_id"], kb["access"]) == (account, ALICE, "owner")
    personal = test_client.get("/knowledge-bases", headers=owner_headers(ALICE_EMAIL)).json()
    assert alices_kb not in {kb["kb_id"] for kb in personal}


def test_other_members_cannot_see_it_until_it_is_shared_and_then_only_read(test_client, account, alices_kb):
    bob = as_(BOB_EMAIL, account)
    assert alices_kb not in listed(test_client, BOB_EMAIL, account)
    assert test_client.get(f"/knowledge-bases/{alices_kb}", headers=bob).status_code == 404

    share(test_client, account, alices_kb, BOB)

    assert listed(test_client, BOB_EMAIL, account)[alices_kb] == "shared"
    assert test_client.get(f"/knowledge-bases/{alices_kb}/crawl-jobs", headers=bob).status_code == 200
    assert test_client.patch(f"/knowledge-bases/{alices_kb}", headers=bob, json={"name": "Mine"}).status_code == 403
    assert test_client.delete(f"/knowledge-bases/{alices_kb}", headers=bob).status_code == 403


def test_admins_see_and_delete_but_not_read_contents(test_client, account, alices_kb):
    admin = as_(ADMIN_EMAIL, account)

    assert listed(test_client, ADMIN_EMAIL, account)[alices_kb] == "admin"
    assert test_client.get(f"/knowledge-bases/{alices_kb}", headers=admin).json()["access"] == "admin"
    assert test_client.get(f"/knowledge-bases/{alices_kb}/crawl-jobs", headers=admin).status_code == 403
    assert test_client.get(f"/knowledge-bases/{alices_kb}/uploads", headers=admin).status_code == 403
    assert test_client.delete(f"/knowledge-bases/{alices_kb}", headers=admin).status_code == 204


def test_nothing_reaches_across_accounts(test_client, account, alices_kb):
    assert test_client.get(f"/knowledge-bases/{alices_kb}", headers=owner_headers(OUTSIDER_EMAIL)).status_code == 404
    assert test_client.get(f"/knowledge-bases/{alices_kb}", headers=as_(OUTSIDER_EMAIL, account)).status_code == 403


def test_an_agent_searches_a_shared_knowledge_base_only_while_its_owner_may_read_it(test_client, account, alices_kb):
    bob = as_(BOB_EMAIL, account)
    agent_id = test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=bob).json()["agent_id"]
    assert test_client.post(f"/agents/{agent_id}/knowledge-bases?kb_id={alices_kb}", headers=bob).status_code == 404

    share(test_client, account, alices_kb, BOB)
    assert test_client.post(f"/agents/{agent_id}/knowledge-bases?kb_id={alices_kb}", headers=bob).status_code == 201
    agent = AgentRepository().find_in_account(account, agent_id)
    assert [kb.kb_id for kb in readable_by_agent(agent, [alices_kb])] == [alices_kb]

    revoked = test_client.delete(f"/knowledge-bases/{alices_kb}/shares/members/{BOB}", headers=as_(ALICE_EMAIL, account))
    assert revoked.status_code in (200, 204), revoked.text
    assert readable_by_agent(agent, [alices_kb]) == [], "the link stays, the reads stop"
    assert test_client.get(f"/agents/{agent_id}/knowledge-bases", headers=bob).json() == []


def test_deleting_a_knowledge_base_forgets_its_shares(test_client, account, alices_kb):
    share(test_client, account, alices_kb, BOB)

    test_client.delete(f"/knowledge-bases/{alices_kb}", headers=as_(ALICE_EMAIL, account))

    assert ShareRepository().on_resource(account, "knowledge-base", alices_kb) == []
    assert test_client.get(f"/knowledge-bases/{alices_kb}", headers=as_(ALICE_EMAIL, account)).status_code == 404
