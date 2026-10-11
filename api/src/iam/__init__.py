"""IAM-style authorization within an account. See docs/LLD-shared-accounts-and-iam.md.

The engine (actions, policy, engine, builtins) is pure: standard library and pydantic only.
"""

from .actions import ACCOUNT, CATALOG, Action, ResourceRef, describe_action_for, expand
from .builtins import BUILTINS
from .engine import Decision, NamedPolicy, Share, evaluate
from .policy import PolicyDocument, Statement

__all__ = [
    "ACCOUNT",
    "BUILTINS",
    "CATALOG",
    "Action",
    "Decision",
    "NamedPolicy",
    "PolicyDocument",
    "ResourceRef",
    "Share",
    "Statement",
    "describe_action_for",
    "evaluate",
    "expand",
]
