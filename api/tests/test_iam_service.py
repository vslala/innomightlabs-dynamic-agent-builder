"""IAM storage and API: groups, policies and versions, attachments, the escalation guard and the
last-admin rule (KAN-77)."""
import pytest
from fastapi.testclient import TestClient

from src.accounts import AccountService, Member
from src.iam.policy import VERSION
from src.iam.repository import IamRepository
from src.iam.service import IamError, IamService
from src.identity import IdentityRepository
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, user_id_for
from tests.oauth_handoff import owner_headers

ADMIN, MEMBER = user_id_for(TEST_USER_EMAIL), user_id_for(TEST_USER_EMAIL_2)
THIRD = user_id_for("someone-else@example.com")


def doc(*statements: dict) -> dict:
    return {"Version": VERSION, "Statement": list(statements)}


def allow(action, resource="*") -> dict:
    return {"Effect": "Allow", "Action": action, "Resource": resource}


def deny(action, resource="*") -> dict:
    return {"Effect": "Deny", "Action": action, "Resource": resource}


@pytest.fixture
def account(dynamodb_table) -> str:
    """An account run by ADMIN, with MEMBER and THIRD as plain members (as after accepting invites)."""
    created = AccountService().create_account(IdentityRepository().get(ADMIN), "Lab")
    for user_id in (MEMBER, THIRD):
        identity = IdentityRepository().get(user_id)
        dynamodb_table.put_item(Item=Member(account_id=created.account_id, user_id=user_id, email=identity.email,
                                            name=identity.name, invited_by=ADMIN).to_dynamo_item())
    return created.account_id


@pytest.fixture
def iam() -> IamService:
    return IamService()


def code_of(raised: pytest.ExceptionInfo) -> str:
    return raised.value.detail["code"]


# Groups and memberships


def test_groups_hold_members_and_are_named_uniquely(account, iam):
    group = iam.create_group(account, ADMIN, "Support")
    iam.add_to_group(account, ADMIN, group.group_id, MEMBER)

    state = iam.state(account, ADMIN)
    assert state.members_of(group.group_id) == [MEMBER]
    assert state.group_ids_of(MEMBER) == {group.group_id}
    with pytest.raises(IamError) as taken:
        iam.create_group(account, ADMIN, "support")
    assert code_of(taken) == "NAME_TAKEN"


def test_deleting_a_group_removes_its_memberships_and_attachments(account, iam, dynamodb_table):
    group = iam.create_group(account, ADMIN, "Support")
    iam.add_to_group(account, ADMIN, group.group_id, MEMBER)
    iam.attach(account, ADMIN, "group", group.group_id, "ViewOnlyAccess")

    iam.delete_group(account, ADMIN, group.group_id)

    keys = {item["sk"] for item in dynamodb_table.scan()["Items"] if item["pk"] == f"Account#{account}"}
    assert not [key for key in keys if group.group_id in key]


# Policies and versions


def test_a_policy_keeps_five_versions_and_never_drops_the_default(account, iam):
    policy = iam.create_policy(account, ADMIN, "Readers", doc(allow("agents:List")))
    for _ in range(6):
        policy = iam.create_version(account, ADMIN, policy.policy_id, doc(allow("agents:Describe")), set_default=False)

    assert sorted(policy.versions) == [1, 4, 5, 6, 7]
    assert policy.default_version == 1
    assert sorted(IamRepository().load(account).policies[policy.policy_id].versions) == [1, 4, 5, 6, 7]


def test_an_invalid_document_is_refused_with_every_problem(account, iam):
    with pytest.raises(IamError) as invalid:
        iam.create_policy(account, ADMIN, "Bad", doc(allow("agents:Fly"), allow("agents:Get", "spaceship/*")))

    assert code_of(invalid) == "INVALID_POLICY"
    assert len(invalid.value.detail["errors"]) == 2


def test_an_attached_policy_cannot_be_deleted(account, iam):
    policy = iam.create_policy(account, ADMIN, "Readers", doc(allow("agents:List")))
    iam.attach(account, ADMIN, "member", MEMBER, policy.ref)

    with pytest.raises(IamError) as attached:
        iam.delete_policy(account, ADMIN, policy.policy_id)
    assert code_of(attached) == "POLICY_ATTACHED"

    iam.detach(account, ADMIN, "member", MEMBER, policy.ref)
    iam.delete_policy(account, ADMIN, policy.policy_id)
    assert iam.state(account, ADMIN).policies == {}


# Who may change what


def test_a_member_cannot_manage_iam(account, iam):
    for change in (
        lambda: iam.create_group(account, MEMBER, "Mine"),
        lambda: iam.create_policy(account, MEMBER, "Mine", doc(allow("agents:List"))),
        lambda: iam.attach(account, MEMBER, "member", MEMBER, "AdministratorAccess"),
        lambda: iam.remove_member(account, MEMBER, ADMIN),
    ):
        with pytest.raises(IamError) as refused:
            change()
        assert code_of(refused) == "ACCESS_DENIED"


def test_holding_attach_alone_does_not_let_you_make_yourself_admin(account, iam):
    attacher = iam.create_policy(account, ADMIN, "Attacher", doc(allow(["iam:AttachPolicies", "iam:ManageGroups"])))
    iam.attach(account, ADMIN, "member", MEMBER, attacher.ref)
    group = iam.create_group(account, ADMIN, "Mine")
    iam.add_to_group(account, ADMIN, group.group_id, MEMBER)

    for change in (
        lambda: iam.attach(account, MEMBER, "member", MEMBER, "AdministratorAccess"),
        lambda: iam.attach(account, MEMBER, "group", group.group_id, "AdministratorAccess"),
    ):
        with pytest.raises(IamError) as refused:
            change()
        assert code_of(refused) == "ESCALATION"
        assert "iam:ManageMembers on *" in refused.value.detail["missing"]


def test_joining_a_group_is_guarded_like_attaching(account, iam):
    """Adding yourself to the admins' group would grant you what the group holds."""
    admins = iam.create_group(account, ADMIN, "Admins")
    iam.attach(account, ADMIN, "group", admins.group_id, "AdministratorAccess")
    grouper = iam.create_policy(account, ADMIN, "Grouper", doc(allow("iam:ManageGroups")))
    iam.attach(account, ADMIN, "member", MEMBER, grouper.ref)

    with pytest.raises(IamError) as refused:
        iam.add_to_group(account, MEMBER, admins.group_id, MEMBER)
    assert code_of(refused) == "ESCALATION"


def test_an_admin_cannot_grant_contents_of_others_resources(account, iam):
    readers = iam.create_policy(account, ADMIN, "Readers", doc(allow("conversations:Read", "conversation/*")))

    with pytest.raises(IamError) as refused:
        iam.attach(account, ADMIN, "member", MEMBER, readers.ref)
    assert code_of(refused) == "ESCALATION"


def test_owner_access_is_implicit(account, iam):
    with pytest.raises(IamError) as refused:
        iam.attach(account, ADMIN, "member", MEMBER, "OwnerAccess")
    assert code_of(refused) == "IMPLICIT_POLICY"


# The account owner


def test_the_owner_cannot_be_removed_detached_or_attached_to(account, iam):
    iam.attach(account, ADMIN, "member", MEMBER, "AdministratorAccess")
    denier = iam.create_policy(account, ADMIN, "NoIam", doc(deny("iam:*")))
    for change in (
        lambda: iam.remove_member(account, MEMBER, ADMIN),
        lambda: iam.detach(account, MEMBER, "member", ADMIN, "AdministratorAccess"),
        lambda: iam.attach(account, MEMBER, "member", ADMIN, denier.ref),
        lambda: iam.remove_member(account, ADMIN, ADMIN),
    ):
        with pytest.raises(IamError) as refused:
            change()
        assert code_of(refused) == "ACCOUNT_OWNER"

    assert ADMIN in iam.state(account, ADMIN).members


def test_the_owners_groups_add_to_their_power_but_never_take_from_it(account, iam):
    """A group the owner is in can't deny them anything, even if its policy is edited to."""
    group = iam.create_group(account, ADMIN, "Everyone")
    iam.add_to_group(account, ADMIN, group.group_id, ADMIN)
    iam.add_to_group(account, ADMIN, group.group_id, MEMBER)
    mixed = iam.create_policy(account, ADMIN, "Mixed", doc(allow("iam:ListGroups"), deny("*")))
    iam.attach(account, ADMIN, "group", group.group_id, mixed.ref)

    state = iam.state(account, ADMIN)
    owner = [(p.policy.name, p.source) for p in state.effective_policies(ADMIN)]
    assert owner[:2] == [("OwnerAccess", "implicit"), ("AdministratorAccess", "account owner")]
    assert all(s.effect == "Allow" for p in state.effective_policies(ADMIN) for s in p.policy.document.statements)
    iam.create_group(account, ADMIN, "Still running the account")
    with pytest.raises(IamError) as denied:
        iam.create_group(account, MEMBER, "Mine")
    assert (code_of(denied), denied.value.detail["reason"]) == ("ACCESS_DENIED", "explicit_deny"), \
        "the Deny still applies to everyone else"


def test_other_admins_can_be_demoted_or_removed(account, iam):
    iam.attach(account, ADMIN, "member", MEMBER, "AdministratorAccess")
    iam.detach(account, ADMIN, "member", MEMBER, "AdministratorAccess")
    iam.attach(account, ADMIN, "member", THIRD, "AdministratorAccess")
    iam.remove_member(account, ADMIN, THIRD)

    state = iam.state(account, ADMIN)
    assert state.attachments_of("member", MEMBER) == [] and THIRD not in state.members


def test_another_admin_cannot_lock_the_owner_out(account, iam, test_client: TestClient):
    """An admin denies iam:* to the owner's only group: the owner can still run IAM."""
    iam.attach(account, ADMIN, "member", MEMBER, "AdministratorAccess")
    group = iam.create_group(account, MEMBER, "Owners")
    iam.add_to_group(account, MEMBER, group.group_id, ADMIN)
    iam.attach(account, MEMBER, "group", group.group_id, iam.create_policy(account, MEMBER, "NoIam", doc(deny("iam:*"))).ref)

    response = test_client.get("/iam/members", headers=as_(TEST_USER_EMAIL, account))

    assert response.status_code == 200, response.text


def test_a_change_judged_on_a_stale_state_is_not_saved(account, iam):
    """Another change landed after this one was judged: it was judged on a state that is gone."""
    stale = IamRepository().load(account)
    iam.create_group(account, ADMIN, "Support")

    with pytest.raises(IamError) as conflict:
        iam.commit(stale, put=[{"pk": f"Account#{account}", "sk": "Group#late", "group_id": "late",
                                 "name": "Late", "created_by": ADMIN, "created_at": "now"}])
    assert code_of(conflict) == "CONFLICT"
    assert [g.name for g in iam.state(account, ADMIN).groups.values()] == ["Support"]


def test_every_change_bumps_the_version(account, iam):
    before = IamRepository().load(account).authz_version

    group = iam.create_group(account, ADMIN, "Support")
    iam.add_to_group(account, ADMIN, group.group_id, MEMBER)

    assert IamRepository().load(account).authz_version == before + 2


def test_removing_a_member_needs_manage_members_and_keeps_the_identity(account, iam):
    iam.remove_member(account, ADMIN, MEMBER)

    assert MEMBER not in iam.state(account, ADMIN).members
    assert IdentityRepository().get(MEMBER) is not None


# Over HTTP


def as_(user_email: str, account_id: str) -> dict[str, str]:
    return {**owner_headers(user_email), "X-Account-Id": account_id}


def test_permissions_change_on_the_members_next_request(account, test_client: TestClient):
    """An admin groups a member under a custom policy; the member's very next request sees it."""
    admin, member = as_(TEST_USER_EMAIL, account), as_(TEST_USER_EMAIL_2, account)
    assert test_client.get("/iam/groups", headers=member).status_code == 403

    policy = test_client.post("/iam/policies", headers=admin, json={
        "name": "Directory", "document": doc(allow(["iam:ListGroups", "iam:ListMembers"])),
    }).json()
    group = test_client.post("/iam/groups", headers=admin, json={"name": "Support"}).json()
    attached = test_client.put(f"/iam/groups/{group['group_id']}/policies/{policy['policy']}", headers=admin)
    joined = test_client.put(f"/iam/groups/{group['group_id']}/members/{MEMBER}", headers=admin)

    assert (attached.status_code, joined.status_code) == (204, 204)
    listed = test_client.get("/iam/groups", headers=member)
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["member_ids"] == [MEMBER]
    sources = {(p["policy"], p["source"]) for p in
               test_client.get(f"/iam/members/{MEMBER}/effective-policies", headers=admin).json()}
    assert sources == {("OwnerAccess", "implicit"), (policy["policy"], f"group:{group['group_id']}")}


def test_rolling_a_policy_back_restores_what_it_allowed(account, test_client: TestClient):
    admin, member = as_(TEST_USER_EMAIL, account), as_(TEST_USER_EMAIL_2, account)
    policy = test_client.post("/iam/policies", headers=admin, json={
        "name": "Directory", "document": doc(allow("iam:ListGroups")),
    }).json()["policy"]
    test_client.put(f"/iam/members/{MEMBER}/policies/{policy}", headers=admin)
    assert test_client.get("/iam/groups", headers=member).status_code == 200

    v2 = test_client.post(f"/iam/policies/{policy}/versions", headers=admin,
                          json={"document": doc(allow("iam:ListMembers")), "set_default": True})
    assert v2.status_code == 201, v2.text
    assert test_client.get("/iam/groups", headers=member).status_code == 403

    rolled = test_client.put(f"/iam/policies/{policy}/default-version", headers=admin, json={"version": 1})
    assert rolled.json()["default_version"] == 1
    assert test_client.get("/iam/groups", headers=member).status_code == 200


def test_a_member_cannot_make_themselves_admin_over_http(account, test_client: TestClient):
    response = test_client.put(f"/iam/members/{MEMBER}/policies/AdministratorAccess",
                               headers=as_(TEST_USER_EMAIL_2, account))

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ACCESS_DENIED"


def test_the_owner_cannot_be_demoted_over_http(account, test_client: TestClient):
    response = test_client.delete(f"/iam/members/{ADMIN}/policies/AdministratorAccess",
                                  headers=as_(TEST_USER_EMAIL, account))

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ACCOUNT_OWNER"


def test_policies_list_the_builtins_then_the_accounts_own(account, test_client: TestClient):
    admin = as_(TEST_USER_EMAIL, account)
    test_client.post("/iam/policies", headers=admin, json={"name": "Directory", "document": doc(allow("iam:ListGroups"))})

    listed = test_client.get("/iam/policies", headers=admin).json()

    assert [(p["name"], p["builtin"]) for p in listed] == [
        ("OwnerAccess", True), ("MemberAccess", True), ("AdministratorAccess", True), ("ViewOnlyAccess", True),
        ("Directory", False),
    ]
    assert next(p for p in listed if p["name"] == "AdministratorAccess")["attachment_count"] == 0, \
        "the owner holds it without an attachment"


def test_validating_a_policy_is_a_dry_run(account, test_client: TestClient):
    member = as_(TEST_USER_EMAIL_2, account)

    good = test_client.post("/iam/policies/validate", headers=member, json={"document": doc(allow("agents:List"))})
    bad = test_client.post("/iam/policies/validate", headers=member, json={"document": doc(allow("agents:Fly"))})

    assert good.json() == {"valid": True, "errors": []}
    assert bad.json()["valid"] is False and "matches no action" in bad.json()["errors"][0]


def test_members_list_their_groups_and_policies(account, test_client: TestClient):
    listed = {m["user_id"]: m for m in test_client.get("/iam/members", headers=as_(TEST_USER_EMAIL, account)).json()}

    assert set(listed) == {ADMIN, MEMBER, THIRD}
    assert (listed[ADMIN]["is_owner"], listed[ADMIN]["policies"]) == (True, [])
    assert listed[MEMBER]["is_owner"] is False
    assert listed[MEMBER]["email"] == TEST_USER_EMAIL_2


def test_the_catalog_is_open_to_any_member(account, test_client: TestClient):
    actions = test_client.get("/iam/actions", headers=as_(TEST_USER_EMAIL_2, account)).json()

    assert {"name": "conversations:Read", "resource_type": "conversation", "touches_contents": True} in actions


def test_someone_outside_the_account_gets_nothing(account, test_client: TestClient):
    outsider = as_("owner@example.com", account)

    response = test_client.get("/iam/actions", headers=outsider)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "NOT_A_MEMBER"
