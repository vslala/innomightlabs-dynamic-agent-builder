from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status

from ..iam.dependencies import get_principal
from ..iam.principal import load_principal
from ..iam.service import IamError
from ..identity import Identity, IdentityRepository
from .models import AccountResponse, ActiveAccountRequest, CreateAccountRequest, MembershipResponse
from .service import AccountService

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _caller(request: Request) -> Identity:
    identity: Optional[Identity] = getattr(request.state, "identity", None)
    if identity is None:
        raise HTTPException(status_code=401, detail="User not authenticated")
    return identity


@router.get("", response_model=list[MembershipResponse])
async def list_accounts(request: Request) -> list[MembershipResponse]:
    """The accounts the caller belongs to, oldest membership first, marking the one requests act in."""
    caller = _caller(request)
    try:
        active: Optional[str] = get_principal(request).account_id
    except IamError:
        active = None
    return [membership.model_copy(update={"active": membership.account_id == active})
            for membership in AccountService().list_accounts(caller.user_id)]


@router.put("/active", response_model=MembershipResponse)
async def switch_account(body: ActiveAccountRequest, request: Request) -> MembershipResponse:
    """Remember the account to act in when a request doesn't name one, on every device."""
    caller = _caller(request)
    load_principal(caller.user_id, body.account_id)  # refuses an account the caller isn't an active member of
    IdentityRepository().set_last_account(caller.user_id, body.account_id)
    chosen = [m for m in AccountService().list_accounts(caller.user_id) if m.account_id == body.account_id]
    return chosen[0].model_copy(update={"active": True})


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(body: CreateAccountRequest, request: Request) -> AccountResponse:
    """A new account; the caller becomes its admin."""
    account = AccountService().create_account(_caller(request), body.name)
    return AccountResponse(
        account_id=account.account_id, name=account.name, status=account.status, created_at=account.created_at
    )
