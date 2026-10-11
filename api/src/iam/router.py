"""The /iam API behind the IAM portal: groups, custom policies and versions, attachments.

Reads are checked against the caller's (cached) permissions; writes are judged again inside the
service, against the state they change.
"""

from typing import Literal

from fastapi import APIRouter, Depends, Response, status

from ..accounts.repository import AccountRepository
from .actions import CATALOG
from .builtins import BUILTINS
from .dependencies import get_principal
from .models import AccountIam, CustomPolicy, Group
from .principal import Principal
from .schemas import (
    ActionResponse,
    DefaultVersionRequest,
    EffectivePolicyResponse,
    GroupRequest,
    GroupResponse,
    GroupUpdate,
    MemberResponse,
    PolicyRequest,
    PolicyResponse,
    PolicySummary,
    PolicyVersionRequest,
    PolicyVersionResponse,
    ValidateRequest,
    ValidateResponse,
)
from .service import IamService, find_group, find_member, find_policy, policy_problems

router = APIRouter(prefix="/iam", tags=["iam"])

def _state(principal: Principal, action: str) -> AccountIam:
    principal.require(action)
    return IamService().state(principal.account_id, principal.user_id)


def _group_response(state: AccountIam, group: Group) -> GroupResponse:
    return GroupResponse(
        group_id=group.group_id, name=group.name, description=group.description, created_at=group.created_at,
        member_ids=state.members_of(group.group_id),
        policies=sorted(a.policy for a in state.attachments_of("group", group.group_id)),
    )


def _attachment_count(state: AccountIam, policy: str) -> int:
    return sum(1 for attachment in state.attachments.values() if attachment.policy == policy)


def _custom_summary(state: AccountIam, policy: CustomPolicy) -> PolicySummary:
    return PolicySummary(policy=policy.ref, name=policy.name, description=policy.description, builtin=False,
                         default_version=policy.default_version, attachment_count=_attachment_count(state, policy.ref))


def _policy_response(state: AccountIam, policy: str) -> PolicyResponse:
    builtin = BUILTINS.get(policy)
    if builtin:
        return PolicyResponse(
            policy=builtin.name, name=builtin.name, description="", builtin=True,
            attachment_count=_attachment_count(state, builtin.name),
            versions=[PolicyVersionResponse(version=1, document=builtin.document.to_json(), is_default=True)],
        )
    custom = find_policy(state, policy)
    return PolicyResponse(
        **_custom_summary(state, custom).model_dump(),
        versions=[
            PolicyVersionResponse(version=v.version, document=v.document.to_json(),
                                  is_default=v.version == custom.default_version, created_at=v.created_at)
            for v in sorted(custom.versions.values(), key=lambda v: v.version)
        ],
    )


# The catalog and members


@router.get("/actions", response_model=list[ActionResponse])
async def list_actions(principal: Principal = Depends(get_principal)) -> list[ActionResponse]:
    """Every action a policy can name, for the visual policy builder."""
    return [ActionResponse(name=a.name, resource_type=a.resource_type, touches_contents=a.touches_contents)
            for a in CATALOG.values()]


@router.get("/members", response_model=list[MemberResponse])
async def list_members(principal: Principal = Depends(get_principal)) -> list[MemberResponse]:
    state = _state(principal, "iam:ListMembers")
    return [
        MemberResponse(
            user_id=member.user_id, email=member.email, name=member.name, status=member.status,
            joined_at=member.joined_at, is_owner=member.user_id == state.owner_id,
            group_ids=sorted(state.group_ids_of(member.user_id)),
            policies=sorted(a.policy for a in state.attachments_of("member", member.user_id)),
        )
        for member in AccountRepository().members(principal.account_id)
    ]


@router.get("/members/{user_id}/effective-policies", response_model=list[EffectivePolicyResponse])
async def effective_policies(user_id: str, principal: Principal = Depends(get_principal)) -> list[EffectivePolicyResponse]:
    """Every policy that applies to the member, and where it comes from."""
    state = _state(principal, "iam:ListPolicies")
    find_member(state, user_id)
    return [EffectivePolicyResponse(policy=e.policy.name, source=e.source, document=e.policy.document.to_json())
            for e in state.effective_policies(user_id)]


# Attachments


@router.put("/{principal_type}/{principal_id}/policies/{policy}", status_code=status.HTTP_204_NO_CONTENT)
async def attach_policy(principal_type: Literal["members", "groups"], principal_id: str, policy: str,
                        principal: Principal = Depends(get_principal)) -> Response:
    IamService().attach(principal.account_id, principal.user_id, _singular(principal_type), principal_id, policy)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{principal_type}/{principal_id}/policies/{policy}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_policy(principal_type: Literal["members", "groups"], principal_id: str, policy: str,
                        principal: Principal = Depends(get_principal)) -> Response:
    IamService().detach(principal.account_id, principal.user_id, _singular(principal_type), principal_id, policy)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _singular(principal_type: str) -> Literal["member", "group"]:
    return "member" if principal_type == "members" else "group"


# Groups


@router.get("/groups", response_model=list[GroupResponse])
async def list_groups(principal: Principal = Depends(get_principal)) -> list[GroupResponse]:
    state = _state(principal, "iam:ListGroups")
    return [_group_response(state, group) for group in sorted(state.groups.values(), key=lambda g: g.name.casefold())]


@router.post("/groups", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(body: GroupRequest, principal: Principal = Depends(get_principal)) -> GroupResponse:
    group = IamService().create_group(principal.account_id, principal.user_id, body.name, body.description)
    return GroupResponse(group_id=group.group_id, name=group.name, description=group.description,
                         created_at=group.created_at, member_ids=[], policies=[])


@router.get("/groups/{group_id}", response_model=GroupResponse)
async def get_group(group_id: str, principal: Principal = Depends(get_principal)) -> GroupResponse:
    state = _state(principal, "iam:ListGroups")
    return _group_response(state, find_group(state, group_id))


@router.patch("/groups/{group_id}", response_model=GroupResponse)
async def update_group(group_id: str, body: GroupUpdate, principal: Principal = Depends(get_principal)) -> GroupResponse:
    service = IamService()
    service.update_group(principal.account_id, principal.user_id, group_id, body.name, body.description)
    state = service.state(principal.account_id, principal.user_id)
    return _group_response(state, find_group(state, group_id))


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group_id: str, principal: Principal = Depends(get_principal)) -> Response:
    IamService().delete_group(principal.account_id, principal.user_id, group_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/groups/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_to_group(group_id: str, user_id: str, principal: Principal = Depends(get_principal)) -> Response:
    IamService().add_to_group(principal.account_id, principal.user_id, group_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/groups/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_group(group_id: str, user_id: str, principal: Principal = Depends(get_principal)) -> Response:
    IamService().remove_from_group(principal.account_id, principal.user_id, group_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Policies


@router.post("/policies/validate", response_model=ValidateResponse)
async def validate_policy(body: ValidateRequest, principal: Principal = Depends(get_principal)) -> ValidateResponse:
    """A dry run for the policy editor."""
    problems = policy_problems(body.document)
    return ValidateResponse(valid=not problems, errors=problems)


@router.get("/policies", response_model=list[PolicySummary])
async def list_policies(principal: Principal = Depends(get_principal)) -> list[PolicySummary]:
    """The built-ins, then the account's own."""
    state = _state(principal, "iam:ListPolicies")
    builtins = [PolicySummary(policy=name, name=name, description="", builtin=True,
                              attachment_count=_attachment_count(state, name)) for name in BUILTINS]
    custom = sorted(state.policies.values(), key=lambda p: p.name.casefold())
    return builtins + [_custom_summary(state, policy) for policy in custom]


@router.post("/policies", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(body: PolicyRequest, principal: Principal = Depends(get_principal)) -> PolicyResponse:
    service = IamService()
    policy = service.create_policy(principal.account_id, principal.user_id, body.name, body.document, body.description)
    return _policy_response(service.state(principal.account_id, principal.user_id), policy.ref)


@router.get("/policies/{policy}", response_model=PolicyResponse)
async def get_policy(policy: str, principal: Principal = Depends(get_principal)) -> PolicyResponse:
    return _policy_response(_state(principal, "iam:ListPolicies"), policy)


@router.delete("/policies/{policy}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(policy: str, principal: Principal = Depends(get_principal)) -> Response:
    IamService().delete_policy(principal.account_id, principal.user_id, policy)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/policies/{policy}/versions", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy_version(policy: str, body: PolicyVersionRequest,
                                principal: Principal = Depends(get_principal)) -> PolicyResponse:
    service = IamService()
    changed = service.create_version(principal.account_id, principal.user_id, policy, body.document, body.set_default)
    return _policy_response(service.state(principal.account_id, principal.user_id), changed.ref)


@router.put("/policies/{policy}/default-version", response_model=PolicyResponse)
async def set_default_version(policy: str, body: DefaultVersionRequest,
                              principal: Principal = Depends(get_principal)) -> PolicyResponse:
    service = IamService()
    changed = service.set_default_version(principal.account_id, principal.user_id, policy, body.version)
    return _policy_response(service.state(principal.account_id, principal.user_id), changed.ref)
