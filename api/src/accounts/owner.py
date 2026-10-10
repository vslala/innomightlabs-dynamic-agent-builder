"""Whose data something is: a member of an account. See docs/LLD-shared-accounts-and-iam.md.

Resources an account shares live under `Account#{account_id}`; a member's private ones under
`Account#{account_id}#Member#{user_id}`. `email` is the member's email: data that hasn't moved into
accounts yet (KAN-80, one type at a time) is still keyed by it.
"""

from dataclasses import dataclass


def member_partition(account_id: str, user_id: str) -> str:
    """A member's private partition in an account: their conversations, and what else is theirs alone."""
    return f"Account#{account_id}#Member#{user_id}"


@dataclass(frozen=True)
class Owner:
    account_id: str
    user_id: str
    email: str

    @property
    def account_pk(self) -> str:
        return f"Account#{self.account_id}"

    @property
    def member_pk(self) -> str:
        return member_partition(self.account_id, self.user_id)

