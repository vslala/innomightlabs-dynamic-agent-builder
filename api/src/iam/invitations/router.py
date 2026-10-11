import asyncio

from fastapi import APIRouter, Depends, Request, Response

from ...identity import Identity
from ..dependencies import get_principal
from ..principal import Principal
from ..service import IamError
from .schemas import AcceptResponse, CreateInvitationRequest, InvitationResponse, PreviewResponse, TokenRequest
from .service import InvitationService

router = APIRouter(tags=["invitations"])


@router.get("/iam/invitations", response_model=list[InvitationResponse])
def list_invitations(principal: Principal = Depends(get_principal)) -> list[InvitationResponse]:
    principal.require("iam:ListMembers")
    service = InvitationService()
    return [InvitationResponse.from_invite(invite, service.clock())
            for invite in service.list_invitations(principal.account_id, principal.user_id)]


# The service reads and writes DynamoDB synchronously, so the async routes below run it in a thread
# rather than stall the event loop for every other request.
@router.post("/iam/invitations", response_model=InvitationResponse, status_code=201)
async def create_invitation(body: CreateInvitationRequest,
                            principal: Principal = Depends(get_principal)) -> InvitationResponse:
    principal.require("iam:Invite")
    service = InvitationService()
    invite, raw = await asyncio.to_thread(service.create, principal.account_id, principal.user_id, str(body.email))
    return InvitationResponse.from_invite(await service.deliver(invite, raw), service.clock())


@router.post("/iam/invitations/{invite_id}/resend", response_model=InvitationResponse)
async def resend_invitation(invite_id: str, principal: Principal = Depends(get_principal)) -> InvitationResponse:
    principal.require("iam:Invite")
    service = InvitationService()
    invite, raw = await asyncio.to_thread(service.resend, principal.account_id, principal.user_id, invite_id)
    return InvitationResponse.from_invite(await service.deliver(invite, raw), service.clock())


@router.delete("/iam/invitations/{invite_id}", status_code=204)
def revoke_invitation(invite_id: str, principal: Principal = Depends(get_principal)) -> Response:
    principal.require("iam:Invite")
    InvitationService().revoke(principal.account_id, principal.user_id, invite_id)
    return Response(status_code=204)


@router.post("/invitations/preview", response_model=PreviewResponse)
def preview_invitation(body: TokenRequest, request: Request) -> PreviewResponse:
    service = InvitationService()
    service.throttle_preview(request.client.host if request.client else None)
    return service.preview(body.token)


@router.post("/invitations/accept", response_model=AcceptResponse)
def accept_invitation(body: TokenRequest, request: Request) -> AcceptResponse:
    identity = getattr(request.state, "identity", None)
    if not isinstance(identity, Identity):
        raise IamError(401, "NOT_AUTHENTICATED", "Sign in to accept this invitation")
    # No principal dependency: an invitee is not yet a member of the target account.
    return InvitationService().accept(body.token, identity)
