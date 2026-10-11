"""Settings and credentials belong to the account (KAN-80, slice 6): its admins connect providers and MCP servers,
every member's agents use them, nothing crosses accounts, and only the default agent is each member's own."""
import pytest
from fastapi.testclient import TestClient

from src.accounts import AccountService, Member
from src.agents.models import Agent
from src.agents.provider_session import ProviderNotConfigured, open_provider_session
from src.agents.repository import AgentRepository
from src.iam.service import IamService
from src.identity import IdentityRepository
from src.settings.repository import ProviderSettingsRepository
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, user_id_for
from tests.oauth_handoff import owner_headers

ADMIN_EMAIL, ALICE_EMAIL, BOB_EMAIL = TEST_USER_EMAIL, TEST_USER_EMAIL_2, "someone-else@example.com"
ALICE, BOB = user_id_for(ALICE_EMAIL), user_id_for(BOB_EMAIL)
ANTHROPIC = {"api_key": "sk-ant-test"}
DOCS_SERVER = {"name": "Docs", "server_url": "https://mcp.example.com/mcp", "auth_type": "none"}


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


def configured(test_client: TestClient, headers: dict[str, str]) -> set[str]:
    providers = test_client.get("/settings/providers", headers=headers).json()
    return {provider["provider_name"] for provider in providers if provider["is_configured"]}


def test_only_admins_connect_a_provider_and_every_member_sees_it(test_client, account):
    assert test_client.post("/settings/providers/Anthropic", json=ANTHROPIC,
                            headers=as_(ALICE_EMAIL, account)).status_code == 403

    saved = test_client.post("/settings/providers/Anthropic", json=ANTHROPIC, headers=as_(ADMIN_EMAIL, account))

    assert saved.status_code == 201, saved.text
    assert "Anthropic" in configured(test_client, as_(ALICE_EMAIL, account))
    assert test_client.delete("/settings/providers/Anthropic", headers=as_(BOB_EMAIL, account)).status_code == 403
    assert "Anthropic" not in configured(test_client, owner_headers(ALICE_EMAIL)), "not in her personal account"


def test_a_promoted_admin_manages_the_accounts_settings(test_client, account):
    def can_manage(email: str) -> bool:
        return test_client.get("/settings/access", headers=as_(email, account)).json()["can_manage"]

    assert (can_manage(ADMIN_EMAIL), can_manage(BOB_EMAIL)) == (True, False)

    IamService().attach(account, user_id_for(ADMIN_EMAIL), "member", BOB, "AdministratorAccess")

    assert can_manage(BOB_EMAIL)
    saved = test_client.post("/settings/providers/Anthropic", json=ANTHROPIC, headers=as_(BOB_EMAIL, account))
    assert saved.status_code == 201, saved.text


async def test_a_members_agent_runs_on_the_accounts_provider(test_client, account):
    agent = AgentRepository().save(Agent(
        agent_name="Helper", agent_architecture="krishna-mini", agent_provider="Anthropic", agent_persona="Hi",
        account_id=account, owner_id=ALICE, created_by=ALICE,
    ))
    with pytest.raises(ProviderNotConfigured):
        await open_provider_session(agent, provider_settings_repo=ProviderSettingsRepository())
    # Alice's own key in her personal account doesn't reach the team's agents
    test_client.post("/settings/providers/Anthropic", json=ANTHROPIC, headers=owner_headers(ALICE_EMAIL))
    with pytest.raises(ProviderNotConfigured):
        await open_provider_session(agent, provider_settings_repo=ProviderSettingsRepository())

    test_client.post("/settings/providers/Anthropic", json=ANTHROPIC, headers=as_(ADMIN_EMAIL, account))

    session = await open_provider_session(agent, provider_settings_repo=ProviderSettingsRepository())
    assert session.credentials == ANTHROPIC


def test_mcp_connections_are_the_accounts(test_client, account):
    assert test_client.post("/connectors/mcp", json=DOCS_SERVER, headers=as_(ALICE_EMAIL, account)).status_code == 403

    created = test_client.post("/connectors/mcp", json=DOCS_SERVER, headers=as_(ADMIN_EMAIL, account))

    assert created.status_code == 201, created.text
    mcp_id = created.json()["mcp_id"]
    assert mcp_id in {c["mcp_id"] for c in test_client.get("/connectors/mcp", headers=as_(ALICE_EMAIL, account)).json()}
    assert test_client.patch(f"/connectors/mcp/{mcp_id}", json={"name": "Mine"},
                             headers=as_(ALICE_EMAIL, account)).status_code == 403
    assert test_client.delete(f"/connectors/mcp/{mcp_id}", headers=as_(BOB_EMAIL, account)).status_code == 403
    assert test_client.get("/connectors/mcp", headers=owner_headers(ALICE_EMAIL)).json() == [], "nor across accounts"


def test_a_member_links_the_accounts_connection_to_their_own_agent(test_client, account):
    mcp_id = test_client.post("/connectors/mcp", json=DOCS_SERVER, headers=as_(ADMIN_EMAIL, account)).json()["mcp_id"]
    agent = AgentRepository().save(Agent(
        agent_name="Helper", agent_architecture="krishna-memgpt", agent_provider="Bedrock", agent_persona="Hi",
        account_id=account, owner_id=ALICE, created_by=ALICE,
    ))

    linked = test_client.put(f"/agents/{agent.agent_id}/mcp-connections/{mcp_id}", json={"enabled": True},
                             headers=as_(ALICE_EMAIL, account))

    assert linked.status_code == 200, linked.text
    links = test_client.get(f"/agents/{agent.agent_id}/mcp-connections", headers=as_(ALICE_EMAIL, account)).json()
    assert [(link["mcp_id"], link["enabled"]) for link in links] == [(mcp_id, True)]


@pytest.mark.parametrize("path, body", [
    ("/dream/settings", {"enabled": False, "cron_expression": "0 3 * * *", "timezone": "UTC"}),
    ("/smart-suggestions/settings", {"enabled": False}),
    ("/settings/agent2agent", {"allowed_origins": {"https://agents.example.com": "Partner"}}),
])
def test_account_wide_settings_are_changed_by_admins_and_read_by_members(test_client, account, path, body):
    assert test_client.put(path, json=body, headers=as_(ALICE_EMAIL, account)).status_code == 403

    saved = test_client.put(path, json=body, headers=as_(ADMIN_EMAIL, account))

    assert saved.status_code == 200, saved.text
    assert test_client.get(path, headers=as_(BOB_EMAIL, account)).json() == saved.json()


def test_the_default_agent_is_each_members_own(test_client, account):
    agent = AgentRepository().save(Agent(
        agent_name="Helper", agent_architecture="krishna-memgpt", agent_provider="Bedrock", agent_persona="Hi",
        account_id=account, owner_id=ALICE, created_by=ALICE,
    ))

    chosen = test_client.put("/settings/default-agent", json={"agent_id": agent.agent_id},
                             headers=as_(ALICE_EMAIL, account))

    assert chosen.status_code == 200, chosen.text
    assert test_client.get("/settings/default-agent", headers=as_(ALICE_EMAIL, account)).json()["agent_id"] == agent.agent_id
    assert test_client.get("/settings/default-agent", headers=as_(ADMIN_EMAIL, account)).json()["agent_id"] is None
    assert test_client.get("/settings/default-agent", headers=owner_headers(ALICE_EMAIL)).json()["agent_id"] is None

