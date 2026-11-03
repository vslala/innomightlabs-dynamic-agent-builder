"""Who an account's work is charged to.

Plans, limits and usage belong to the account's owner, not to whoever does the work: a member creating an agent,
chatting or crawling in a shared account uses the owner's quota, and an owner on the superuser list exempts the
whole account. Until billing moves to accounts (KAN-86) the quota is still keyed by the owner's email.
"""

from typing import Optional

from ..accounts.repository import AccountRepository


def account_billing_email(account_id: str) -> Optional[str]:
    """The email of the account's owner, or None when the account or its owner can't be found."""
    accounts = AccountRepository()
    account = accounts.get(account_id)
    owner = accounts.get_member(account_id, account.owner_id) if account else None
    return owner.email if owner else None
