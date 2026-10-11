"""Agents in shared accounts (KAN-80): private by default, shared on purpose, admins see metadata only,
nothing crosses accounts, and an agent always runs as its owner."""
import pytest
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from src.accounts import AccountService, Member
from src.iam.service import IamService
from src.iam.shares import ShareRepository
from src.identity import IdentityRepository
from src.public_api.auth import require_secret_key
from src.public_api.keys import AgentSecretKey, SecretKeyRepository
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
        # What accepting an invite attaches by default
        IamService().attach(created.account_id, user_id_for(ADMIN_EMAIL), "member", identity.user_id, "MemberAccess")
    return created.account_id


def as_(email: str, account: str) -> dict[str, str]:
    return {**owner_headers(email), "X-Account-Id": account}


@pytest.fixture
def alices_agent(account, test_client: TestClient) -> str:
    response = test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=as_(ALICE_EMAIL, account))
    assert response.status_code == 201, response.text
    return response.json()["agent_id"]


def listed(test_client: TestClient, email: str, account: str) -> dict[str, str]:
    return {a["agent_id"]: a["access"] for a in test_client.get("/agents", headers=as_(email, account)).json()}


def test_an_agent_is_created_in_the_account_the_request_acts_in(test_client, account, alices_agent):
    agent = test_client.get(f"/agents/{alices_agent}", headers=as_(ALICE_EMAIL, account)).json()

    assert (agent["account_id"], agent["owner_id"], agent["access"]) == (account, ALICE, "owner")
    personal = test_client.get("/agents", headers=owner_headers(ALICE_EMAIL)).json()
    assert alices_agent not in {a["agent_id"] for a in personal}, "her personal account doesn't have it"


def test_other_members_cannot_see_an_agent_until_it_is_shared(test_client, account, alices_agent):
    bob = as_(BOB_EMAIL, account)
    assert alices_agent not in listed(test_client, BOB_EMAIL, account)
    assert test_client.get(f"/agents/{alices_agent}", headers=bob).status_code == 404

    shared = test_client.put(f"/agents/{alices_agent}/shares/members/{BOB}", headers=as_(ALICE_EMAIL, account),
                             json={"preset": "user"})

    assert shared.status_code == 200, shared.text
    assert listed(test_client, BOB_EMAIL, account)[alices_agent] == "shared"
    agent = test_client.get(f"/agents/{alices_agent}", headers=bob).json()
    assert agent["agent_persona"] == AGENT_CREATE_REQUEST["agent_persona"], "User includes Get"


def test_a_user_share_chats_but_cannot_edit_delete_or_reshare(test_client, account, alices_agent):
    bob = as_(BOB_EMAIL, account)
    test_client.put(f"/agents/{alices_agent}/shares/members/{BOB}", headers=as_(ALICE_EMAIL, account),
                    json={"preset": "user"})

    conversation = test_client.post("/conversations/", headers=bob, json={"title": "Bob's", "agent_id": alices_agent})
    edited = test_client.put(f"/agents/{alices_agent}", headers=bob, json={"agent_persona": "Mine now"})
    deleted = test_client.delete(f"/agents/{alices_agent}", headers=bob)
    reshared = test_client.put(f"/agents/{alices_agent}/shares/members/{user_id_for(ADMIN_EMAIL)}", headers=bob,
                               json={"preset": "viewer"})

    assert conversation.status_code == 201, conversation.text
    assert (edited.status_code, deleted.status_code, reshared.status_code) == (403, 403, 403)


def test_a_shared_agent_runs_as_its_owner_for_the_member_chatting(test_client, account, alices_agent, monkeypatch):
    bob = as_(BOB_EMAIL, account)
    test_client.put(f"/agents/{alices_agent}/shares/members/{BOB}", headers=as_(ALICE_EMAIL, account),
                    json={"preset": "user"})
    conversation_id = test_client.post("/conversations/", headers=bob,
                                       json={"title": "Bob's", "agent_id": alices_agent}).json()["conversation_id"]
    started = {}

    def fake_start_turn(**kwargs):
        started.update(kwargs)
        raise RuntimeError("stop here")

    monkeypatch.setattr("src.agents.router.start_turn", fake_start_turn)
    with pytest.raises(RuntimeError, match="stop here"):
        test_client.post(f"/agents/{alices_agent}/{conversation_id}/send-message", headers=bob, json={"content": "hi"})

    assert (started["owner_email"], started["actor_email"]) == (ALICE_EMAIL, BOB_EMAIL)
    assert started["actor_kind"].value == "member", "owner-only skills and tools don't reach a member"


def test_admins_see_and_manage_metadata_but_not_contents(test_client, account, alices_agent):
    admin = as_(ADMIN_EMAIL, account)

    assert listed(test_client, ADMIN_EMAIL, account)[alices_agent] == "admin"
    agent = test_client.get(f"/agents/{alices_agent}", headers=admin).json()
    assert (agent["access"], agent["agent_persona"]) == ("admin", "")
    conversation = test_client.post("/conversations/", headers=admin, json={"title": "x", "agent_id": alices_agent})
    assert conversation.status_code == 403, "chatting is contents"
    assert test_client.put(f"/agents/{alices_agent}", headers=admin, json={"agent_persona": "x"}).status_code == 403
    assert test_client.delete(f"/agents/{alices_agent}", headers=admin).status_code == 204


def test_nothing_reaches_across_accounts(test_client, account, alices_agent):
    outsider = owner_headers(OUTSIDER_EMAIL)  # acting in their own personal account

    assert test_client.get(f"/agents/{alices_agent}", headers=outsider).status_code == 404
    assert test_client.delete(f"/agents/{alices_agent}", headers=outsider).status_code == 404
    assert test_client.get(f"/agents/{alices_agent}", headers=as_(OUTSIDER_EMAIL, account)).status_code == 403, \
        "naming an account you aren't in gets nothing"


def test_a_secret_key_acts_as_the_agents_owner_whoever_created_it(test_client, account, alices_agent):
    key, secret = AgentSecretKey.issue(agent_id=alices_agent, name="ci", created_by=user_id_for(ADMIN_EMAIL))
    SecretKeyRepository().create(key)

    caller = require_secret_key(alices_agent, HTTPAuthorizationCredentials(scheme="Bearer", credentials=secret))

    assert caller.owner_email == ALICE_EMAIL


def test_deleting_an_agent_forgets_its_shares(test_client, account, alices_agent):
    alice = as_(ALICE_EMAIL, account)
    test_client.put(f"/agents/{alices_agent}/shares/members/{BOB}", headers=alice, json={"preset": "viewer"})

    test_client.delete(f"/agents/{alices_agent}", headers=alice)

    assert ShareRepository().on_resource(account, "agent", alices_agent) == []


def test_a_conversation_on_a_shared_agent_is_the_members_alone(test_client, account, alices_agent):
    """Sharing an agent shares chatting with it, not anyone's chats: not with its owner, not with an admin."""
    bob = as_(BOB_EMAIL, account)
    test_client.put(f"/agents/{alices_agent}/shares/members/{BOB}", headers=as_(ALICE_EMAIL, account),
                    json={"preset": "user"})
    conversation_id = test_client.post("/conversations/", headers=bob,
                                       json={"title": "Bob's", "agent_id": alices_agent}).json()["conversation_id"]

    def listed_conversations(email: str) -> set[str]:
        page = test_client.get("/conversations/", headers=as_(email, account)).json()
        return {c["conversation_id"] for c in page["items"]}

    assert conversation_id in listed_conversations(BOB_EMAIL)
    for other in (ALICE_EMAIL, ADMIN_EMAIL):
        assert conversation_id not in listed_conversations(other)
        assert test_client.get(f"/conversations/{conversation_id}", headers=as_(other, account)).status_code == 404
        assert test_client.delete(f"/conversations/{conversation_id}", headers=as_(other, account)).status_code == 404
    assert test_client.get(f"/conversations/{conversation_id}", headers=bob).status_code == 200


def test_a_conversation_stays_in_the_account_it_was_started_in(test_client, account, alices_agent):
    conversation_id = test_client.post("/conversations/", headers=as_(ALICE_EMAIL, account),
                                       json={"title": "Team", "agent_id": alices_agent}).json()["conversation_id"]
    personal = owner_headers(ALICE_EMAIL)

    assert conversation_id not in {c["conversation_id"] for c in test_client.get("/conversations/", headers=personal)
                                   .json()["items"]}
    assert test_client.get(f"/conversations/{conversation_id}", headers=personal).status_code == 404
