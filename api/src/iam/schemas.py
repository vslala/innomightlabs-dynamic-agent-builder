"""Request and response bodies for /iam."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Request(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class GroupRequest(_Request):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


class GroupUpdate(_Request):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)


class PolicyRequest(_Request):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    document: dict[str, Any]


class PolicyVersionRequest(_Request):
    document: dict[str, Any]
    set_default: bool = False


class DefaultVersionRequest(_Request):
    version: int = Field(ge=1)


class ValidateRequest(_Request):
    document: dict[str, Any]


class ActionResponse(BaseModel):
    name: str
    resource_type: str
    touches_contents: bool


class CapabilitiesResponse(BaseModel):
    can_list_members: bool
    can_invite: bool


class MemberResponse(BaseModel):
    user_id: str
    email: str
    name: str
    status: str
    joined_at: str
    is_owner: bool
    group_ids: list[str]
    policies: list[str]


class GroupResponse(BaseModel):
    group_id: str
    name: str
    description: str
    member_ids: list[str]
    policies: list[str]
    created_at: str


class PolicySummary(BaseModel):
    policy: str  # what attachments name: a built-in name or custom:{policy_id}
    name: str
    description: str
    builtin: bool
    default_version: Optional[int] = None
    attachment_count: int


class PolicyVersionResponse(BaseModel):
    version: int
    document: dict[str, Any]
    is_default: bool
    created_at: Optional[str] = None


class PolicyResponse(PolicySummary):
    versions: list[PolicyVersionResponse]


class EffectivePolicyResponse(BaseModel):
    policy: str
    source: str  # "implicit", "direct" or "group:{group_id}"
    document: dict[str, Any]


class ValidateResponse(BaseModel):
    valid: bool
    errors: list[str]


class ShareRequest(_Request):
    """A preset, or (advanced) the actions to grant, each one the sharer holds."""

    preset: Optional[Literal["viewer", "user", "editor"]] = None
    actions: Optional[list[str]] = Field(default=None, min_length=1)


class ShareResponse(BaseModel):
    resource_type: str
    resource_id: str
    grantee_type: str
    grantee_id: str
    actions: list[str]
    preset: Optional[str]
    granted_by: str
    granted_at: str
