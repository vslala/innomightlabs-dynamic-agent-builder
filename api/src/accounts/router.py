from fastapi import APIRouter, HTTPException, Request, status

from ..identity import Identity, IdentityRepository
from .models import AccountResponse, CreateAccountRequest, MembershipResponse
from .service import AccountService

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _caller(request: Request) -> Identity:
    user_id = getattr(request.state, "user_id", None)
    identity = IdentityRepository().get(user_id) if user_id else None
    if identity is None:
        raise HTTPException(status_code=401, detail="User not authenticated")
    return identity


@router.get("", response_model=list[MembershipResponse])
async def list_accounts(request: Request) -> list[MembershipResponse]:
    """The accounts the caller belongs to, oldest membership first."""
    return AccountService().list_accounts(_caller(request).user_id)


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(body: CreateAccountRequest, request: Request) -> AccountResponse:
    """A new account; the caller becomes its admin."""
    account = AccountService().create_account(_caller(request), body.name)
    return AccountResponse(
        account_id=account.account_id, name=account.name, status=account.status, created_at=account.created_at
    )
