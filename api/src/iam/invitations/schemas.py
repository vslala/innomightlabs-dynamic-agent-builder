from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import DeliveryStatus, Invite, InviteStatus


class CreateInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=320)


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    token: str = Field(min_length=43, max_length=128, repr=False)


class InvitationResponse(BaseModel):
    account_id: str
    invite_id: str
    email: str
    invited_by: str
    expires_at: str
    status: InviteStatus
    delivery_status: DeliveryStatus
    accepted_by: str | None
    created_at: str

    @classmethod
    def from_invite(cls, invite: Invite, timestamp: float) -> "InvitationResponse":
        return cls(**{name: getattr(invite, name) for name in cls.model_fields
                      if name != "status"}, status=invite.effective_status(timestamp))


class PreviewResponse(BaseModel):
    account_id: str
    account_name: str
    email: str
    expires_at: str
    status: InviteStatus
    login_context: str


class AcceptResponse(BaseModel):
    account_id: str
    invite_id: str
