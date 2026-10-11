"""Sharing one resource with a member or a group (KAN-78). Resources come from a stand-in resolver until
they live in accounts (KAN-80)."""
import pytest
from fastapi.testclient import TestClient

from src.accounts import AccountService, Member
from src.iam import ResourceRef
from src.iam.policy import VERSION
from src.iam.principal import load_principal
from src.iam.service import IamError, IamService
from src.iam.shares import PRESETS, RESOLVERS, ShareRepository, ShareService, shareable_actions
from src.identity import IdentityRepository
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, user_id_for
from tests.oauth_handoff import owner_headers

OWNER = user_id_for(TEST_USER_EMAIL)  # owns the account
ALICE = user_id_for(TEST_USER_EMAIL_2)  # owns the agent
BOB = user_id_for("someone-else@example.com")
OUTSIDER = user_id_for("owner@example.com")
AGENT = ResourceRef("agent", "a1", ALICE)


@pytest.fixture
def account(dynamodb_table, monkeypatch) -> str:
    created = AccountService().create_account(IdentityRepository().get(OWNER), "Lab")
    for user_id in (ALICE, BOB):
        identity = IdentityRepository().get(user_id)
        dynamodb_table.put_item(Item=Member(account_id=created.account_id, user_id=user_id, email=identity.email,
                                            name=identity.name, invited_by=OWNER).to_dynamo_item())
    agents = {AGENT.id: AGENT}
    monkeypatch.setitem(RESOLVERS, "agent", lambda account_id, rid: agents.get(rid) if account_id == created.account_id else None)
    return created.account_id


@pytest.fixture
def shares() -> ShareService:
    return ShareService()


def can(account: str, user_id: str, action: str, resource: ResourceRef = AGENT) -> bool:
    """As the member's next request would decide it."""
    return load_principal(user_id, account).can(action, resource).allowed


def code_of(raised: pytest.ExceptionInfo) -> str:
    return raised.value.detail["code"]


def test_a_user_share_lets_bob_chat_but_not_edit_delete_or_reshare(account, shares):
    shares.share(account, ALICE, AGENT, "member", BOB, preset="user")

    assert [can(account, BOB, action) for action in ("agents:Describe", "agents:Get", "agents:Chat")] == [True] * 3
    assert [can(account, BOB, action) for action in ("agents:Update", "agents:Delete", "agents:Share")] == [False] * 3
    assert load_principal(BOB, account).can("agents:Chat", AGENT).reason == "share"
    with pytest.raises(IamError) as reshare:
        shares.share(account, BOB, AGENT, "member", OWNER, preset="viewer")
    assert code_of(reshare) == "ACCESS_DENIED", "Bob can see the agent, so he is told no rather than not found"


def test_resources_stay_private_until_shared(account, shares):
    assert not can(account, BOB, "agents:Describe")
    with pytest.raises(IamError) as hidden:
        shares.share(account, BOB, AGENT, "member", BOB, preset="viewer")
    assert code_of(hidden) == "NOT_FOUND", "someone who can't see a resource isn't told it exists"


def test_a_group_share_reaches_its_members_until_they_leave(account, shares):
    iam = IamService()
    group = iam.create_group(account, OWNER, "Support")
    iam.add_to_group(account, OWNER, group.group_id, BOB)
    shares.share(account, ALICE, AGENT, "group", group.group_id, preset="user")
    assert can(account, BOB, "agents:Chat")

    iam.remove_from_group(account, OWNER, group.group_id, BOB)

    assert not can(account, BOB, "agents:Chat")


def test_revoking_takes_effect_on_the_next_request(account, shares):
    shares.share(account, ALICE, AGENT, "member", BOB, preset="editor")
    assert can(account, BOB, "agents:Update")

    shares.revoke(account, ALICE, AGENT, "member", BOB)

    assert not can(account, BOB, "agents:Describe")


def test_sharing_again_replaces_access(account, shares):
    shares.share(account, ALICE, AGENT, "member", BOB, preset="editor")
    shares.share(account, ALICE, AGENT, "member", BOB, preset="viewer")

    assert not can(account, BOB, "agents:Chat")
    assert [s.preset for s in shares.who_has_access(account, ALICE, AGENT)] == ["viewer"]


def test_you_can_only_share_what_you_can_do(account, shares):
    """Bob may re-share, but holds only the User actions: he can pass those on, not Editor's."""
    shares.share(account, ALICE, AGENT, "member", BOB, actions=[*PRESETS["agent"]["user"], "agents:Share"])

    with pytest.raises(IamError) as escalation:
        shares.share(account, BOB, AGENT, "member", OWNER, preset="editor")
    assert code_of(escalation) == "ESCALATION"
    assert escalation.value.detail["missing"] == ["agents:Update", "skills:Configure"]

    shares.share(account, BOB, AGENT, "member", OWNER, preset="user")
    assert can(account, OWNER, "agents:Chat")


def test_a_deny_on_share_stops_sharing_even_your_own(account, shares):
    iam = IamService()
    no_sharing = iam.create_policy(account, OWNER, "NoSharing", {
        "Version": VERSION, "Statement": [{"Effect": "Deny", "Action": "*:Share", "Resource": "*"}],
    })
    iam.attach(account, OWNER, "member", ALICE, no_sharing.ref)

    with pytest.raises(IamError) as denied:
        shares.share(account, ALICE, AGENT, "member", BOB, preset="viewer")
    assert (code_of(denied), denied.value.detail["reason"]) == ("ACCESS_DENIED", "explicit_deny")


def test_an_admin_sees_metadata_but_cannot_share_others_resources(account, shares):
    """The account owner holds AdministratorAccess: Describe, not Share or contents."""
    assert can(account, OWNER, "agents:Describe") and not can(account, OWNER, "agents:Get")

    with pytest.raises(IamError) as denied:
        shares.share(account, OWNER, AGENT, "member", BOB, preset="viewer")
    assert code_of(denied) == "ACCESS_DENIED"


def test_only_members_and_groups_of_the_account_can_be_granted(account, shares):
    for grantee_type, grantee_id in (("member", OUTSIDER), ("group", "no-such-group")):
        with pytest.raises(IamError) as missing:
            shares.share(account, ALICE, AGENT, grantee_type, grantee_id, preset="viewer")
        assert code_of(missing) == "NOT_FOUND"


@pytest.mark.parametrize("actions", [["agents:Transfer"], ["agents:Create"], ["knowledge:Get"], ["agents:Fly"]])
def test_advanced_shares_pick_only_actions_on_the_resource(account, shares, actions):
    with pytest.raises(IamError) as invalid:
        shares.share(account, ALICE, AGENT, "member", BOB, actions=actions)
    assert code_of(invalid) == "INVALID_SHARE"


def test_presets_never_include_delete_transfer_or_share():
    for resource_type, presets in PRESETS.items():
        for actions in presets.values():
            assert set(actions) <= set(shareable_actions(resource_type))
            assert not [a for a in actions if a.split(":")[1] in ("Delete", "Transfer", "Share")]


def test_conversations_are_never_shared(account, shares):
    with pytest.raises(IamError) as refused:
        shares.share(account, ALICE, ResourceRef("conversation", "c1", ALICE), "member", BOB, preset="viewer")
    assert code_of(refused) == "NOT_SHAREABLE"


def test_shared_with_me_lists_direct_and_group_shares(account, shares):
    iam = IamService()
    group = iam.create_group(account, OWNER, "Support")
    iam.add_to_group(account, OWNER, group.group_id, BOB)
    other = ResourceRef("agent", "a2", ALICE)
    RESOLVERS["agent"] = lambda _account, rid: {"a1": AGENT, "a2": other}.get(rid)
    shares.share(account, ALICE, AGENT, "member", BOB, preset="viewer")
    shares.share(account, ALICE, other, "group", group.group_id, preset="user")

    found = ShareRepository().shared_with(account, BOB, [group.group_id])

    assert {(s.resource_id, s.grantee) for s in found} == {("a1", f"member/{BOB}"), ("a2", f"group/{group.group_id}")}


def test_deleting_a_resource_forgets_its_shares(account, shares):
    shares.share(account, ALICE, AGENT, "member", BOB, preset="viewer")
    shares.share(account, ALICE, AGENT, "member", OWNER, preset="viewer")

    shares.forget_resource(account, "agent", "a1")

    assert ShareRepository().on_resource(account, "agent", "a1") == []
    assert not can(account, BOB, "agents:Describe")


# Over HTTP


def as_(email: str, account: str) -> dict[str, str]:
    return {**owner_headers(email), "X-Account-Id": account}


def test_sharing_over_http(account, test_client: TestClient):
    alice = as_(TEST_USER_EMAIL_2, account)

    shared = test_client.put(f"/agents/a1/shares/members/{BOB}", headers=alice, json={"preset": "user"})
    listed = test_client.get("/agents/a1/shares", headers=alice)
    revoked = test_client.delete(f"/agents/a1/shares/members/{BOB}", headers=alice)

    assert shared.status_code == 200, shared.text
    assert shared.json()["actions"] == list(PRESETS["agent"]["user"])
    assert [(s["grantee_type"], s["grantee_id"], s["preset"]) for s in listed.json()] == [("member", BOB, "user")]
    assert revoked.status_code == 204
    assert test_client.get("/agents/a1/shares", headers=alice).json() == []


def test_an_unknown_resource_is_not_found_over_http(account, test_client: TestClient):
    response = test_client.get("/agents/nope/shares", headers=as_(TEST_USER_EMAIL_2, account))

    assert response.status_code == 404


def test_a_share_needs_a_preset_or_actions(account, test_client: TestClient):
    response = test_client.put(f"/agents/a1/shares/members/{BOB}", headers=as_(TEST_USER_EMAIL_2, account), json={})

    assert response.status_code == 422
