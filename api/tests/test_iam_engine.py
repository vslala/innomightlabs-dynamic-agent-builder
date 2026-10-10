"""The policy engine: catalog, policy grammar, evaluation (KAN-76). Pure, so no fixtures."""
import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.iam import (
    ACCOUNT,
    BUILTINS,
    CATALOG,
    NamedPolicy,
    PolicyDocument,
    ResourceRef,
    Share,
    describe_action_for,
    evaluate,
    expand,
)
from src.iam.policy import OWNER_CONDITION, VERSION

ALICE, BOB = "alice", "bob"
OWNER, MEMBER, ADMIN, VIEW_ONLY = (BUILTINS[name] for name in
                                   ("OwnerAccess", "MemberAccess", "AdministratorAccess", "ViewOnlyAccess"))

ALICES_AGENT = ResourceRef("agent", "a1", ALICE)
BOBS_AGENT = ResourceRef("agent", "b1", BOB)
ALICES_CONVERSATION = ResourceRef("conversation", "c1", ALICE)
ANY_AGENT = ResourceRef("agent")  # Create and List name no agent
THE_ACCOUNT = ResourceRef(ACCOUNT)


def policy(*statements: dict, name: str = "custom:p1") -> NamedPolicy:
    return NamedPolicy(name, PolicyDocument.model_validate({"Version": VERSION, "Statement": list(statements)}))


def allow(action, resource="*", **extra) -> dict:
    return {"Effect": "Allow", "Action": action, "Resource": resource, **extra}


def deny(action, resource="*", **extra) -> dict:
    return {"Effect": "Deny", "Action": action, "Resource": resource, **extra}


def share(*actions: str, grantee: str = f"member/{BOB}") -> Share:
    return Share(frozenset(actions), grantee)


CASES = [
    # (why, caller, action, resource, policies, shares, expected reason)
    ("nothing attached refuses", BOB, "agents:Get", ALICES_AGENT, [], [], "implicit_deny"),
    ("an owner does anything with their own", ALICE, "agents:Update", ALICES_AGENT, [OWNER], [], "allow"),
    ("others' resources are private by default", BOB, "agents:Get", ALICES_AGENT, [OWNER, MEMBER], [], "implicit_deny"),
    ("the owner condition never holds on *", ALICE, "agents:Create", ANY_AGENT, [OWNER], [], "implicit_deny"),
    ("the owner condition never holds on the account", ALICE, "iam:Invite", THE_ACCOUNT, [OWNER], [], "implicit_deny"),
    ("members create their own", BOB, "agents:Create", ANY_AGENT, [OWNER, MEMBER], [], "allow"),
    ("members see the directory", BOB, "iam:ListMembers", THE_ACCOUNT, [MEMBER], [], "allow"),
    ("members don't run the account", BOB, "iam:Invite", THE_ACCOUNT, [OWNER, MEMBER], [], "implicit_deny"),
    ("a share grants its actions", BOB, "agents:Chat", ALICES_AGENT, [OWNER, MEMBER], [share("agents:Chat")], "share"),
    ("a share grants only its actions", BOB, "agents:Update", ALICES_AGENT, [OWNER, MEMBER],
     [share("agents:Describe", "agents:Get", "agents:Chat")], "implicit_deny"),
    ("a group's share counts", BOB, "agents:Get", ALICES_AGENT, [MEMBER],
     [share("agents:Get", grantee="group/support")], "share"),
    ("deny beats an allow in the same policy", ALICE, "agents:Delete", ALICES_AGENT,
     [policy(allow("agents:*"), deny("agents:Delete"))], [], "explicit_deny"),
    ("deny beats an allow from another policy", ALICE, "agents:Update", ALICES_AGENT,
     [OWNER, policy(deny("agents:*"))], [], "explicit_deny"),
    ("deny beats a share", BOB, "agents:Chat", ALICES_AGENT,
     [MEMBER, policy(deny("agents:Chat", "agent/a1"))], [share("agents:Chat")], "explicit_deny"),
    ("a deny on Share stops sharing your own", ALICE, "agents:Share", ALICES_AGENT,
     [OWNER, policy(deny("*:Share"))], [], "explicit_deny"),
    ("a deny only for what you own", ALICE, "agents:Delete", ALICES_AGENT,
     [ADMIN, policy(deny("agents:Delete", Condition=OWNER_CONDITION))], [], "explicit_deny"),
    ("...leaves what others own", ALICE, "agents:Delete", BOBS_AGENT,
     [ADMIN, policy(deny("agents:Delete", Condition=OWNER_CONDITION))], [], "allow"),
    ("service wildcard", BOB, "automations:Run", ResourceRef("automation", "x", ALICE),
     [policy(allow("automations:*"))], [], "allow"),
    ("verb wildcard", BOB, "knowledge:List", ResourceRef("knowledge-base"), [policy(allow("*:List"))], [], "allow"),
    ("verb wildcard matches only that verb", BOB, "knowledge:Get", ResourceRef("knowledge-base", "k", ALICE),
     [policy(allow("*:List"))], [], "implicit_deny"),
    ("type wildcard covers every one of the type", BOB, "agents:Get", ALICES_AGENT,
     [policy(allow("agents:Get", "agent/*"))], [], "allow"),
    ("type wildcard covers id-less agent actions", BOB, "agents:List", ANY_AGENT,
     [policy(allow("agents:List", "agent/*"))], [], "allow"),
    ("type wildcard is only that type", BOB, "knowledge:Get", ResourceRef("knowledge-base", "k", ALICE),
     [policy(allow("*", "agent/*"))], [], "implicit_deny"),
    ("an exact resource", BOB, "agents:Chat", ALICES_AGENT, [policy(allow("agents:Chat", ["agent/zz", "agent/a1"]))],
     [], "allow"),
    ("an exact resource is only that one", BOB, "agents:Chat", BOBS_AGENT, [policy(allow("agents:Chat", "agent/a1"))],
     [], "implicit_deny"),
    ("account actions take *, not a type", BOB, "billing:View", THE_ACCOUNT, [policy(allow("billing:*", "agent/*"))],
     [], "implicit_deny"),
    ("admins manage the account", ALICE, "iam:AttachPolicies", THE_ACCOUNT, [ADMIN], [], "allow"),
    ("admins see others' conversations exist", ALICE, "conversations:Describe", ResourceRef("conversation", "c2", BOB),
     [OWNER, ADMIN], [], "allow"),
    ("admins can delete others' conversations", ALICE, "conversations:Delete", ResourceRef("conversation", "c2", BOB),
     [OWNER, ADMIN], [], "allow"),
    ("admins can transfer others' agents", ALICE, "agents:Transfer", BOBS_AGENT, [OWNER, ADMIN], [], "allow"),
    ("admins can't read others' conversations", ALICE, "conversations:Read", ResourceRef("conversation", "c2", BOB),
     [OWNER, ADMIN], [], "implicit_deny"),
    ("admins can't open others' agents", ALICE, "agents:Get", BOBS_AGENT, [OWNER, ADMIN], [], "implicit_deny"),
    ("...but read their own", ALICE, "conversations:Read", ALICES_CONVERSATION, [OWNER, ADMIN], [], "allow"),
    ("Create on * doesn't reach keys on others' agents", BOB, "apikeys:CreateKey", ALICES_AGENT,
     [OWNER, MEMBER, ADMIN], [], "implicit_deny"),
    ("view-only sees what exists", BOB, "agents:Describe", ALICES_AGENT, [VIEW_ONLY], [], "allow"),
    ("view-only sees the directory", BOB, "iam:ListPolicies", THE_ACCOUNT, [VIEW_ONLY], [], "allow"),
    ("view-only changes nothing", BOB, "iam:Invite", THE_ACCOUNT, [VIEW_ONLY], [], "implicit_deny"),
]


@pytest.mark.parametrize("why, caller, action, resource, policies, shares, expected", CASES, ids=[c[0] for c in CASES])
def test_evaluate(why, caller, action, resource, policies, shares, expected):
    decision = evaluate(caller, action, resource, policies, lambda: shares)

    assert decision.reason == expected
    assert decision.allowed == (expected in ("allow", "share"))


def test_a_decision_says_which_statement_decided():
    denying = policy(allow("agents:*", Sid="UseAgents"), deny("agents:Delete", Sid="KeepAgents"))

    assert evaluate(ALICE, "agents:Delete", ALICES_AGENT, [denying]).sid == "KeepAgents"
    allowed = evaluate(ALICE, "agents:Get", ALICES_AGENT, [OWNER, denying])
    assert (allowed.policy, allowed.sid) == ("OwnerAccess", "EverythingOnWhatYouOwn")
    assert evaluate(BOB, "agents:Get", ALICES_AGENT, [], lambda: [share("agents:Get")]).policy == f"member/{BOB}"


def test_shares_are_not_read_when_a_policy_decides():
    def no_reads():
        raise AssertionError("shares were loaded")

    assert evaluate(ALICE, "agents:Get", ALICES_AGENT, [OWNER], no_reads).allowed
    assert not evaluate(ALICE, "agents:Get", ALICES_AGENT, [policy(deny("*"))], no_reads).allowed
    assert not evaluate(ALICE, "agents:List", ANY_AGENT, [], no_reads).allowed, "nothing to share without an id"


@pytest.mark.parametrize("action, resource", [
    ("agents:Fly", ALICES_AGENT),
    ("conversations:Read", ALICES_AGENT),
    ("iam:Invite", ANY_AGENT),
])
def test_asking_about_an_action_that_does_not_apply_is_a_bug(action, resource):
    with pytest.raises(ValueError):
        evaluate(ALICE, action, resource, [OWNER])


def test_administrator_access_holds_no_contents_action():
    granted = {name for statement in ADMIN.document.statements for pattern in statement.actions for name in expand(pattern)}

    assert granted and not [name for name in granted if CATALOG[name].touches_contents]


def test_every_resource_type_can_be_described():
    for action in CATALOG.values():
        if action.resource_type != ACCOUNT:
            assert describe_action_for(action.resource_type) in CATALOG


def test_documents_accept_one_or_many_and_keep_their_shape():
    document = PolicyDocument.model_validate({
        "Version": VERSION,
        "Statement": {"Sid": "One", "Effect": "Allow", "Action": "agents:Get", "Resource": "agent/a1"},
    })

    assert document.to_json() == {"Version": VERSION, "Statement": [
        {"Sid": "One", "Effect": "Allow", "Action": ["agents:Get"], "Resource": ["agent/a1"]},
    ]}
    assert PolicyDocument.model_validate(document.to_json()) == document


@pytest.mark.parametrize("statement, message", [
    (allow("agents:Fly"), "matches no action"),
    (allow("nothing:*"), "matches no action"),
    (allow("agents"), "is not an action"),
    (allow("agents:Ge?"), "is not an action"),
    (allow("agents:Get", "agent"), "is not a resource"),
    (allow("agents:Get", "agent/a1/extra"), "is not a resource"),
    (allow("agents:Get", "spaceship/*"), "is not a resource type"),
    (allow("agents:Get", "account/*"), "is not a resource type"),
    (allow("agents:Get", "arn:aws:iam::123:agent/a1"), "is not a resource"),
    (allow("agents:Get", Condition={"StringEquals": {"iml:ResourceOwner": "bob"}}), "only supported condition"),
    (allow("agents:Get", Condition={"IpAddress": {"aws:SourceIp": "1.2.3.4"}}), "only supported condition"),
    (allow([]), "at least 1"),
    ({"Effect": "Maybe", "Action": "agents:Get", "Resource": "*"}, "Allow"),
    ({"Effect": "Allow", "Action": "agents:Get", "Resource": "*", "Principal": "*"}, "Extra inputs"),
])
def test_the_validator_explains_what_is_wrong(statement, message):
    with pytest.raises(ValidationError, match=message):
        PolicyDocument.model_validate({"Version": VERSION, "Statement": [statement]})


@pytest.mark.parametrize("document", [
    {"Version": "2012-10-17", "Statement": [allow("agents:Get")]},
    {"Version": VERSION, "Statement": []},
    {"Statement": [allow("agents:Get")]},
])
def test_documents_need_the_v1_version_and_a_statement(document):
    with pytest.raises(ValidationError):
        PolicyDocument.model_validate(document)


def test_the_engine_uses_only_the_standard_library_and_pydantic():
    engine = Path(__file__).parent.parent / "src" / "iam"
    allowed = {"pydantic", "fnmatch", "dataclasses", "re", "typing"}
    for module in ("actions.py", "policy.py", "engine.py", "builtins.py"):
        for node in ast.walk(ast.parse((engine / module).read_text())):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = {(node.module or "").split(".")[0]}
            else:
                continue
            assert names <= allowed, f"{module} imports {names - allowed}"
