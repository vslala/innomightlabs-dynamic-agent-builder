from typing import Optional

from fastapi import Request

from ..accounts.repository import AccountRepository
from ..identity import Identity, IdentityRepository
from .principal import Principal, load_principal
from .service import IamError

ACCOUNT_HEADER = "X-Account-Id"


def get_principal(request: Request) -> Principal:
    """
    The caller acting in one account: the one `X-Account-Id` names, else the account they used last,
    else their oldest membership. A named account they don't belong to is refused (403 NOT_A_MEMBER),
    so a forged header gets nothing; the fallbacks quietly skip accounts they have since left.
    """
    cached: Optional[Principal] = getattr(request.state, "principal", None)
    if cached is not None:
        return cached
    identity = _identity(request)
    named = request.headers.get(ACCOUNT_HEADER)
    principal = load_principal(identity.user_id, named) if named else _fallback(identity)
    request.state.principal = principal
    return principal


def _identity(request: Request) -> Identity:
    identity: Optional[Identity] = getattr(request.state, "identity", None)
    if identity is None:
        user_id = getattr(request.state, "user_id", None)
        identity = IdentityRepository().get(str(user_id)) if user_id else None
    if identity is None:
        raise IamError(401, "NOT_AUTHENTICATED", "Not authenticated")
    return identity


def _fallback(identity: Identity) -> Principal:
    if identity.last_account_id:
        try:
            return load_principal(identity.user_id, identity.last_account_id)
        except IamError:
            pass
    memberships = sorted(
        (m for m in AccountRepository().list_memberships(identity.user_id) if m.status == "active"),
        key=lambda member: member.joined_at,
    )
    for member in memberships:
        if member.account_id != identity.last_account_id:
            return load_principal(identity.user_id, member.account_id)
    raise IamError(403, "NO_ACCOUNT", "You don't belong to any account")
