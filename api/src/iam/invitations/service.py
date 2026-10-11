import asyncio
import secrets
import time
from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal
from typing import Any, NamedTuple
from uuid import uuid4

from pydantic import EmailStr, TypeAdapter

from ...accounts.models import Member
from ...config import settings
from ...email import helpers as email_helpers
from ...identity import Identity, normalize_email
from ...identity.models import email_index_key
from ...rate_limits.limiter import RateLimiter
from ...rate_limits.policy import RateLimitPolicy
from ..actions import ACCOUNT, ResourceRef
from ..engine import evaluate
from ..models import AccountIam
from ..repository import ConcurrentChange
from ..service import IamError
from .models import Invite, iso_timestamp, token_digest
from .repository import InvitationRepository
from .schemas import AcceptResponse, PreviewResponse


def unavailable() -> IamError:
    """One answer for an unknown, expired, revoked or rotated invitation, so nothing says which."""
    return IamError(404, "INVALID_INVITATION", "This invitation is not available")


def conflict() -> IamError:
    return IamError(409, "CONFLICT", "The account changed while saving; try again")


class Snapshot(NamedTuple):
    """One consistent read of an account: what a change is decided on, and what its transaction guards."""

    state: AccountIam
    account: dict[str, Any]
    members: list[dict[str, Any]]
    invites: list[Invite]


class InvitationService:
    """Every method here is blocking DynamoDB I/O except `deliver`; async callers run them in a thread."""

    def __init__(self, repository: InvitationRepository | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.repository = repository or InvitationRepository()
        self.clock = clock

    def _account(self, account_id: str) -> dict[str, Any]:
        account = self.repository.account(account_id)
        if not account or account.get("status") != "active":
            raise IamError(409, "ACCOUNT_INACTIVE", "The account is not active")
        return account

    def _snapshot(self, account_id: str, caller: str | None = None, action: str = "iam:Invite") -> Snapshot:
        """The caller is authorized against this fresh state, not the cached principal: the transaction
        that follows is conditioned on the same `authz_version`, so a revoked admin cannot slip a change in."""
        state = self.repository.iam.load(account_id)
        account = self._account(account_id)
        if state is None or state.authz_version != int(account.get("authz_version", 1)):
            raise conflict()
        if caller is not None:
            if state.members.get(caller) != "active":
                raise IamError(403, "NOT_A_MEMBER", "You are not an active member of this account")
            if not evaluate(caller, action, ResourceRef(ACCOUNT), state.policies_for(caller)).allowed:
                raise IamError(403, "ACCESS_DENIED", f"You are not allowed {action}")
        members = [item for item in self.repository.prefix(account_id, "Member#") if "#Group#" not in item["sk"]]
        return Snapshot(state, account, members, self.repository.invites(account_id))

    @staticmethod
    def _seat_limit(account: dict[str, Any]) -> int:
        value = account.get("seat_limit")
        # DynamoDB numbers arrive as Decimal. Booleans, strings and fractions are not seat counts.
        if isinstance(value, bool) or not isinstance(value, (int, Decimal)) or value <= 0 or value != int(value):
            raise IamError(409, "SEAT_LIMIT_UNAVAILABLE", "The account has no valid seat limit")
        return int(value)

    def _capacity(self, account: dict[str, Any], members: list[dict[str, Any]], invites: list[Invite],
                  *, additional: int) -> int:
        seats = self._seat_limit(account)
        pending = sum(invite.effective_status(self.clock()) == "pending" for invite in invites)
        if len(members) + pending + additional > seats:
            raise IamError(409, "SEAT_LIMIT_REACHED", "The account has no available seats")
        if pending + additional > settings.account_invite_pending_limit:
            raise IamError(409, "PENDING_LIMIT_REACHED", "The account has too many pending invitations")
        return seats

    def _not_member(self, account_id: str, email: str, members: list[dict[str, Any]]) -> None:
        index = self.repository.get_item(email_index_key(email))
        for member in members:
            if normalize_email(member["email"]) == email or (index and index["user_id"] == member["user_id"]):
                raise IamError(409, "ALREADY_MEMBER", "This person is already a member of the account")

    def _no_duplicate(self, email: str, invites: list[Invite], exclude: str | None = None) -> None:
        if any(invite.invite_id != exclude and invite.email == email
               and invite.effective_status(self.clock()) == "pending" for invite in invites):
            raise IamError(409, "INVITATION_EXISTS", "There is already a pending invitation for this email")

    def _commit(self, state: AccountIam, account: dict[str, Any], operations: list[dict[str, Any]],
                seats: int | None = None) -> None:
        condition = "#account_status = :active"
        values: dict[str, Any] = {":active": "active"}
        if seats is not None:
            condition += " AND seat_limit = :seats"
            values[":seats"] = seats
        try:
            self.repository.iam.commit(state, operations=operations, account_condition=condition,
                                       account_values=values, account_names={"#account_status": "status"})
        except ConcurrentChange as error:
            # A single bounded attempt: callers can retry, but no stale authorization is reused.
            raise conflict() from error

    @staticmethod
    def _throttle(account_id: str) -> tuple[RateLimiter, Any]:
        limiter = RateLimiter(RateLimitPolicy.sliding_window(
            "ACCOUNT_INVITES", limit=settings.account_invite_rate_limit,
            seconds=settings.account_invite_rate_window_seconds, fail_open=False))
        decision = limiter.acquire(account_id)
        if not decision.allowed:
            raise IamError(429, "INVITATION_RATE_LIMITED", "Too many invitation attempts",
                           retry_after_seconds=decision.retry_after_seconds)
        return limiter, decision

    def _normalised(self, email: str) -> str:
        return normalize_email(str(TypeAdapter(EmailStr).validate_python(email)))

    def _issue(self, account_id: str, caller: str, snapshot: Snapshot, email: str,
               previous: Invite | None = None) -> tuple[Invite, str]:
        """Persist a new invitation, or `previous` again under a rotated token. Returns the raw token,
        which exists only here and in the email."""
        state, account, members, invites = snapshot
        self._not_member(account_id, email, members)
        self._no_duplicate(email, invites, previous.invite_id if previous else None)
        additional = 0 if previous and previous.effective_status(self.clock()) == "pending" else 1
        seats = self._capacity(account, members, invites, additional=additional)
        timestamp = self.clock()
        expiry = timestamp + settings.account_invite_expiry_days * 86400
        raw = secrets.token_urlsafe(32)
        invite = Invite(account_id=account_id, invite_id=previous.invite_id if previous else str(uuid4()),
                        email=email, invited_by=caller, expires_at=iso_timestamp(expiry), ttl=int(expiry),
                        token_hash=token_digest(raw),
                        created_at=previous.created_at if previous else iso_timestamp(timestamp))
        limiter, decision = self._throttle(account_id)
        try:
            self._commit(state, account, [self.repository.put_invite(invite, previous)], seats)
        except Exception:
            limiter.release(decision)
            raise
        # Once persisted, the slot covers the mail attempt too, even if delivery fails.
        return invite, raw

    def create(self, account_id: str, caller: str, email: str) -> tuple[Invite, str]:
        snapshot = self._snapshot(account_id, caller)
        return self._issue(account_id, caller, snapshot, self._normalised(email))

    def resend(self, account_id: str, caller: str, invite_id: str) -> tuple[Invite, str]:
        snapshot = self._snapshot(account_id, caller)
        previous = self._find(snapshot.invites, invite_id)
        if previous.status not in {"pending", "expired"}:
            raise IamError(409, "INVITATION_NOT_PENDING", "Only pending or expired invitations can be resent")
        return self._issue(account_id, caller, snapshot, self._normalised(previous.email), previous)

    @staticmethod
    def _find(invites: list[Invite], invite_id: str) -> Invite:
        invite = next((item for item in invites if item.invite_id == invite_id), None)
        if invite is None:
            raise unavailable()
        return invite

    async def deliver(self, invite: Invite, raw: str) -> Invite:
        """Email the link and record the outcome. A failed email keeps the invitation (resend rotates the
        token) and raises 502 with its id. Returns the stored invitation once it is delivered."""
        account = await asyncio.to_thread(self.repository.account, invite.account_id)
        sent = False
        try:
            sent = await email_helpers.send_account_invitation_email_safe(
                to_email=invite.email, account_name=account["name"] if account else "",
                invited_by=invite.invited_by,
                invite_url=f'{settings.frontend_url.rstrip("/")}/invitations/accept#token={raw}',
                expires_at=invite.expires_at,
            )
        except Exception:
            # The URL carries the token and an exception can carry the URL: never log it.
            sent = False
        marked = await asyncio.to_thread(self.repository.mark_delivery, invite, "sent" if sent else "failed")
        if not sent:
            raise IamError(502, "INVITATION_DELIVERY_FAILED", "Invitation saved, but email delivery failed",
                           invite_id=invite.invite_id)
        if marked:
            return replace(invite, delivery_status="sent")
        current = await asyncio.to_thread(self.repository.get, invite.account_id, invite.invite_id)
        if current is None:
            raise IamError(409, "CONFLICT", "The invitation changed during delivery")
        return current

    def list_invitations(self, account_id: str, caller: str) -> list[Invite]:
        return self._snapshot(account_id, caller, "iam:ListMembers").invites

    def revoke(self, account_id: str, caller: str, invite_id: str) -> None:
        state, account, _, invites = self._snapshot(account_id, caller)
        invite = self._find(invites, invite_id)
        if invite.status == "revoked":
            return
        if invite.status == "accepted":
            raise IamError(409, "INVITATION_ACCEPTED", "An accepted invitation cannot be revoked")
        self._commit(state, account, [self.repository.put_invite(replace(invite, status="revoked"), invite)])

    def _lookup(self, token_hash: str, *, pending_only: bool = False) -> Invite:
        invite = self.repository.by_hash(token_hash)
        if not invite or invite.effective_status(self.clock()) not in ({"pending"} if pending_only else {"pending", "accepted"}):
            raise unavailable()
        self._account(invite.account_id)
        return invite

    def pending_by_hash(self, token_hash: str) -> Invite:
        """OAuth handoff: only hashes, an active account and a live pending invitation."""
        return self._lookup(token_hash, pending_only=True)

    def throttle_preview(self, client_host: str | None) -> None:
        """The preview is public, so it is limited per client address and fails closed. The address is the
        ASGI peer: X-Forwarded-For is untrusted unless the deployment's proxy handling says otherwise."""
        if client_host is None:
            raise IamError(429, "INVITATION_RATE_LIMITED", "Client address unavailable")
        decision = RateLimiter(RateLimitPolicy.sliding_window(
            "INVITATION_PREVIEW", limit=settings.invitation_preview_rate_limit,
            seconds=settings.invitation_preview_rate_window_seconds, fail_open=False)).acquire(client_host)
        if not decision.allowed:
            raise IamError(429, "INVITATION_RATE_LIMITED", "Too many preview attempts",
                           retry_after_seconds=decision.retry_after_seconds)

    def preview(self, token: str) -> PreviewResponse:
        invite = self._lookup(token_digest(token))
        account = self._account(invite.account_id)
        return PreviewResponse(account_id=invite.account_id, account_name=account["name"], email=invite.email,
                               expires_at=invite.expires_at, status=invite.status, login_context=invite.token_hash)

    def _verified_identity(self, user_id: str, email: str) -> tuple[Identity, dict[str, Any]]:
        item = self.repository.get_item({"pk": f"Identity#{user_id}", "sk": "Identity#Metadata"})
        if not item or item.get("status") != "active" or item.get("email_verified") is not True:
            raise IamError(403, "EMAIL_NOT_VERIFIED", "An active identity with a verified email is required")
        if normalize_email(item["email"]) != email:
            raise IamError(403, "INVITATION_EMAIL_MISMATCH", "Sign in with the invited email address")
        return Identity.from_dynamo_item(item), self.repository.identity_unchanged(item)

    def accept(self, token: str, identity: Identity) -> AcceptResponse:
        token_hash = token_digest(token)
        located = self._lookup(token_hash)
        state, account, members, invites = self._snapshot(located.account_id)
        invite = next((item for item in invites if item.invite_id == located.invite_id), None)
        if not invite or invite.token_hash != token_hash or invite.effective_status(self.clock()) not in {"pending", "accepted"}:
            raise unavailable()
        current, identity_unchanged = self._verified_identity(identity.user_id, invite.email)
        seats = self._capacity(account, members, invites, additional=0)
        member = next((item for item in members if item["user_id"] == current.user_id), None)
        if invite.status == "accepted":
            if invite.accepted_by != current.user_id or not member or member.get("status") != "active":
                raise IamError(409, "MEMBERSHIP_UNAVAILABLE", "This invitation no longer grants membership")
            # Repeat accepts never recreate removed/suspended memberships and validate all reads atomically.
            self._commit(state, account, [identity_unchanged, self.repository.member_active(member),
                                          self.repository.accepted_by(invite, token_hash, current.user_id)], seats)
        else:
            self._not_member(invite.account_id, invite.email, members)
            membership = Member(account_id=invite.account_id, user_id=current.user_id, email=current.email,
                                name=current.name, invited_by=invite.invited_by)
            accepted = replace(invite, status="accepted", accepted_by=current.user_id)
            self._commit(state, account, [
                identity_unchanged, self.repository.put_member(membership),
                self.repository.put_accepted_invite(accepted, invite, self.clock()),
            ], seats)
        return AcceptResponse(account_id=invite.account_id, invite_id=invite.invite_id)
