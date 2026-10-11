"""The escalation guard: you can only grant what you hold (KAN-77). Pure, so no fixtures."""
import pytest

from src.iam import BUILTINS, NamedPolicy, PolicyDocument
from src.iam.guard import ungrantable
from src.iam.policy import OWNER_CONDITION, VERSION

OWNER, MEMBER, ADMIN, VIEW_ONLY = (BUILTINS[name] for name in
                                   ("OwnerAccess", "MemberAccess", "AdministratorAccess", "ViewOnlyAccess"))


def document(*statements: dict) -> PolicyDocument:
    return PolicyDocument.model_validate({"Version": VERSION, "Statement": list(statements)})


def held(*statements: dict) -> NamedPolicy:
    return NamedPolicy("custom:held", document(*statements))


def allow(action, resource="*", **extra) -> dict:
    return {"Effect": "Allow", "Action": action, "Resource": resource, **extra}


def deny(action, resource="*") -> dict:
    return {"Effect": "Deny", "Action": action, "Resource": resource}


CASES = [
    # (why, caller's policies, what they grant, may grant)
    ("an admin grants admin", [OWNER, ADMIN], ADMIN.document, True),
    ("an admin grants the member and view-only built-ins", [OWNER, ADMIN], MEMBER.document, True),
    ("...and view-only", [OWNER, ADMIN], VIEW_ONLY.document, True),
    ("a member can't grant admin", [OWNER, MEMBER], ADMIN.document, False),
    ("holding only AttachPolicies isn't holding admin", [OWNER, held(allow("iam:AttachPolicies"))], ADMIN.document, False),
    ("an admin can't grant contents of others' resources", [OWNER, ADMIN],
     document(allow("conversations:Read", "conversation/*")), False),
    ("...nor on one resource (until ownership and shares count, KAN-78/80)", [OWNER, ADMIN],
     document(allow("agents:Chat", "agent/a1")), False),
    ("OwnerAccess doesn't let you grant everything on *", [OWNER], document(allow("agents:Get")), False),
    ("an owner-conditioned grant is within OwnerAccess", [OWNER], document(allow("*", Condition=OWNER_CONDITION)), True),
    ("denies grant nothing", [OWNER], document(deny("*")), True),
    ("a broader pattern covers a narrower one", [held(allow("agents:Chat", "agent/*"))],
     document(allow("agents:Chat", "agent/a1")), True),
    ("* on an agent action is every agent", [held(allow("agents:Chat", "agent/*"))],
     document(allow("agents:Chat")), True),
    ("a narrower pattern doesn't cover a broader one", [held(allow("agents:Chat", "agent/a1"))],
     document(allow("agents:Chat", "agent/*")), False),
    ("exactly what you hold", [held(allow("agents:Chat", "agent/a1"))], document(allow("agents:Chat", "agent/a1")), True),
    ("a deny you hold blocks granting it", [held(allow("agents:*"), deny("agents:Delete", "agent/a1"))],
     document(allow("agents:Delete", "agent/*")), False),
    ("a deny elsewhere doesn't", [held(allow("agents:*"), deny("agents:Delete", "agent/a1"))],
     document(allow("agents:Delete", "agent/a2")), True),
    ("a resource the action can't act on grants nothing", [OWNER],
     document(allow("agents:Get", "knowledge-base/*")), True),
    ("service wildcards are expanded", [OWNER, ADMIN], document(allow("billing:*")), True),
    ("...including what isn't held", [held(allow("billing:View"))], document(allow("billing:*")), False),
]


@pytest.mark.parametrize("why, caller, granted, may", CASES, ids=[case[0] for case in CASES])
def test_ungrantable(why, caller, granted, may):
    assert (not ungrantable(caller, granted)) is may


def test_the_guard_says_what_is_missing():
    missing = ungrantable([held(allow("billing:View"))], document(allow("billing:*")))

    assert missing == ["billing:Manage on *"]
