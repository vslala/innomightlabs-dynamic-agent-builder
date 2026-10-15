"""Built-in policies: defined here, referred to by name, never stored per account, so improving one
improves it everywhere. See docs/LLD-shared-accounts-and-iam.md, "Built-in policies".
"""

from .engine import NamedPolicy
from .policy import OWNER_CONDITION, VERSION, PolicyDocument


def _policy(name: str, *statements: dict) -> NamedPolicy:
    return NamedPolicy(name, PolicyDocument.model_validate({"Version": VERSION, "Statement": list(statements)}))


# Attached implicitly to every member and never detached: everything on what you own. This is what keeps
# resources private by default.
OWNER_ACCESS = _policy("OwnerAccess", {
    "Sid": "EverythingOnWhatYouOwn", "Effect": "Allow", "Action": "*", "Resource": "*",
    "Condition": OWNER_CONDITION,
})

# Given to people who accept an invite: create your own resources, and see the directory to share with
MEMBER_ACCESS = _policy("MemberAccess", {
    "Sid": "CreateAndListYourOwn", "Effect": "Allow",
    "Action": ["*:Create", "*:List", "iam:ListMembers", "iam:ListGroups", "leads:ListForms"], "Resource": "*",
})

# The account's admins. No contents actions: on other members' resources an admin sees and manages
# metadata only, and reaches contents only through ownership or a share.
ADMINISTRATOR_ACCESS = _policy("AdministratorAccess", {
    "Sid": "RunTheAccount", "Effect": "Allow",
    "Action": ["iam:*", "billing:*", "audit:*", "account:*", "settings:*", "leads:*",
               "*:Create", "*:List", "*:Describe", "*:Transfer", "*:Delete"],
    "Resource": "*",
})

VIEW_ONLY_ACCESS = _policy("ViewOnlyAccess", {
    "Sid": "SeeWhatExists", "Effect": "Allow", "Action": ["*:List", "*:Describe", "iam:List*", "leads:ListForms"],
    "Resource": "*",
})

BUILTINS: dict[str, NamedPolicy] = {
    policy.name: policy for policy in (OWNER_ACCESS, MEMBER_ACCESS, ADMINISTRATOR_ACCESS, VIEW_ONLY_ACCESS)
}
