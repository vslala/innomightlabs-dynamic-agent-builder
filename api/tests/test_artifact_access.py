"""Artifacts, tool jobs and marketplace publishing in shared accounts (KAN-80, slice 7): an artifact is its member's
own in one account, a shared agent's file goes to whoever's conversation it is, a job is checked against the
agent's owner, and publishing an agent takes the right to share it."""
import boto3
import pytest
from fastapi.testclient import TestClient

from src.accounts import AccountService, Member
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.agents.tool_runtime.jobs.models import ToolJob
from src.agents.tool_runtime.jobs.repository import ToolJobRepository
from src.agents.tool_runtime.jobs.service import ToolJobService
from src.artifacts.service import ArtifactService, run_artifact_holder
from src.conversations.models import ApiConversation, Conversation
from src.conversations.repository import ConversationRepository
from src.iam.service import IamService
from src.identity import IdentityRepository
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, user_id_for
from tests.oauth_handoff import owner_headers

ADMIN_EMAIL, ALICE_EMAIL, BOB_EMAIL = TEST_USER_EMAIL, TEST_USER_EMAIL_2, "someone-else@example.com"
ALICE, BOB = user_id_for(ALICE_EMAIL), user_id_for(BOB_EMAIL)
BUCKET = "innomightlabs-conversations-meta"


@pytest.fixture
def account(dynamodb_table, monkeypatch) -> str:
    """Owned by ADMIN; Alice and Bob are members with MemberAccess, as after accepting invites."""
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", BUCKET)
    created = AccountService().create_account(IdentityRepository().get(user_id_for(ADMIN_EMAIL)), "Team")
    for email in (ALICE_EMAIL, BOB_EMAIL):
        identity = IdentityRepository().find_by_email(email)
        dynamodb_table.put_item(Item=Member(account_id=created.account_id, user_id=identity.user_id,
                                            email=email, name=identity.name).to_dynamo_item())
        IamService().attach(created.account_id, user_id_for(ADMIN_EMAIL), "member", identity.user_id, "MemberAccess")
    return created.account_id


@pytest.fixture
def alices_agent(account) -> Agent:
    return AgentRepository().save(Agent(
        agent_name="Helper", agent_architecture="krishna-memgpt", agent_provider="Bedrock", agent_persona="Hi",
        account_id=account, owner_id=ALICE, created_by=ALICE,
    ))


def as_(email: str, account: str) -> dict[str, str]:
    return {**owner_headers(email), "X-Account-Id": account}


def artifact_of(account: str, user_id: str) -> str:
    return ArtifactService().create_artifact(
        account_id=account, user_id=user_id, artifact_type="text", title="Notes", filename="notes.txt",
        mime_type="text/plain", body=b"hello",
    ).artifact_id


def listed(test_client: TestClient, headers: dict[str, str]) -> set[str]:
    return {item["artifact_id"] for item in test_client.get("/artifacts", headers=headers).json()["items"]}


def test_an_artifact_is_its_members_own_in_its_account(test_client, account):
    artifact_id = artifact_of(account, ALICE)

    assert artifact_id in listed(test_client, as_(ALICE_EMAIL, account))
    assert test_client.get(f"/artifacts/{artifact_id}/content", headers=as_(ALICE_EMAIL, account)).content == b"hello"
    for other in (as_(BOB_EMAIL, account), as_(ADMIN_EMAIL, account), owner_headers(ALICE_EMAIL)):
        assert artifact_id not in listed(test_client, other)
        assert test_client.get(f"/artifacts/{artifact_id}", headers=other).status_code == 404


def test_a_shared_agents_file_belongs_to_whoever_is_chatting(account, alices_agent):
    bobs_chat = ConversationRepository().save(Conversation(
        title="Chat", agent_id=alices_agent.agent_id, account_id=account, created_by=BOB,
    ))
    context = {"account_id": account, "owner_id": ALICE, "conversation_id": bobs_chat.conversation_id}

    assert run_artifact_holder(context) == (account, BOB)


def test_a_keys_run_files_to_the_agents_owner(account, alices_agent):
    keys_chat = ConversationRepository().save(ApiConversation.start(
        api_key_id="key-1", account_id=account, agent_id=alices_agent.agent_id, title="API",
    ))

    holder = run_artifact_holder({"account_id": account, "owner_id": ALICE, "conversation_id": keys_chat.conversation_id})

    assert holder == (account, ALICE)


def test_a_job_is_found_only_for_the_owner_it_ran_as(account, alices_agent):
    job = ToolJobRepository().create(ToolJob(
        account_id=account, owner_id=ALICE, actor_email=ALICE_EMAIL, actor_id=ALICE_EMAIL,
        agent_id=alices_agent.agent_id, conversation_id="c1", tool_name="execute_skill_action",
    ))

    def check(account_id: str, owner_id: str) -> dict:
        return ToolJobService().check_job_for_agent(
            job_id=job.job_id, account_id=account_id, owner_id=owner_id, owner_email=ALICE_EMAIL,
            actor_email=ALICE_EMAIL, agent_id=alices_agent.agent_id, conversation_id="c1",
        )

    assert check(account, ALICE)["job_id"] == job.job_id
    for account_id, owner_id in ((account, BOB), ("another-account", ALICE)):
        with pytest.raises(ValueError, match="not found"):
            check(account_id, owner_id)


def test_publishing_an_agent_takes_the_right_to_share_it(test_client, account, alices_agent):
    body = {"agent_id": alices_agent.agent_id, "title": "Helper", "short_description": "Helps",
            "full_description": "Helps", "tags": [], "included_skill_ids": [], "status": "published"}
    shared = test_client.put(f"/agents/{alices_agent.agent_id}/shares/members/{BOB}",
                             headers=as_(ALICE_EMAIL, account), json={"preset": "editor"})
    assert shared.status_code == 200, shared.text

    assert test_client.post("/agent-marketplace/agents/publish", json=body,
                            headers=as_(BOB_EMAIL, account)).status_code == 403
    published = test_client.post("/agent-marketplace/agents/publish", json=body, headers=as_(ALICE_EMAIL, account))
    assert published.status_code == 201, published.text

    template_id = published.json()["template_id"]
    assert test_client.post(f"/agent-marketplace/agents/{template_id}/archive",
                            headers=as_(BOB_EMAIL, account)).status_code == 404
    assert test_client.post(f"/agent-marketplace/agents/{template_id}/archive",
                            headers=as_(ALICE_EMAIL, account)).status_code == 200
