import logging
from typing import Optional

from ..identity import Identity
from .models import ADMINISTRATOR_ACCESS, Account, Member, MembershipResponse, personal_account_id
from .repository import AccountExists, AccountRepository

log = logging.getLogger(__name__)

PERSONAL_ACCOUNT_NAME = "Personal"


class AccountService:
    def __init__(self, repository: Optional[AccountRepository] = None) -> None:
        self.repository = repository or AccountRepository()

    def create_account(self, creator: Identity, name: str, account_id: Optional[str] = None) -> Account:
        """A new account with the creator as its only member and admin."""
        account = Account(name=name, created_by=creator.user_id)
        if account_id:
            account.account_id = account_id
        admin = Member(account_id=account.account_id, user_id=creator.user_id, email=creator.email, name=creator.name)
        self.repository.create(account, admin)
        log.info("Created account %s for %s", account.account_id, creator.user_id)
        return account

    def ensure_personal_account(self, identity: Identity) -> Optional[Account]:
        """
        Give a person who belongs to no account their personal one; returns it if it was created now.
        Runs at every sign-in rather than only the first, so an identity whose first sign-in failed part
        way, or that predates accounts, still ends up with somewhere to work.
        """
        if self.repository.list_memberships(identity.user_id):
            return None
        try:
            return self.create_account(identity, PERSONAL_ACCOUNT_NAME, account_id=personal_account_id(identity.user_id))
        except AccountExists:
            # A concurrent sign-in created it first
            return None

    def list_accounts(self, user_id: str) -> list[MembershipResponse]:
        memberships = self.repository.list_memberships(user_id)
        accounts = self.repository.get_many(member.account_id for member in memberships)
        listed = []
        for member in memberships:
            account = accounts.get(member.account_id)
            if account is None:
                continue
            policies = self.repository.member_policies(member.account_id, user_id)
            listed.append(MembershipResponse(
                account_id=account.account_id,
                name=account.name,
                access_summary="admin" if ADMINISTRATOR_ACCESS in policies else "member",
                membership_status=member.status,
                joined_at=member.joined_at,
            ))
        return sorted(listed, key=lambda membership: membership.joined_at)

    def remove_member(self, account_id: str, user_id: str) -> None:
        """Removal only; who may remove whom (and the last-admin rule) belongs to the IAM service (KAN-77)."""
        self.repository.remove_member(account_id, user_id)
        log.info("Removed member %s from account %s", user_id, account_id)
