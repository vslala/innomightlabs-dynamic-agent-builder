"""
Kits: everything one blueprint built, with its versions.

Endpoints:
    GET  /kits                          The person's kits, most recently changed first
    GET  /kits/{id}                     What it holds, and every version
    POST /kits/{id}/rollback/plan       What going back to a version would do; nothing happens yet
    POST /kits/{id}/rollback            Go back, if it's still the plan the person saw
    POST /kits/{id}/removal/plan        What removing the kit would delete
    POST /kits/{id}/remove              Remove it, if it's still the plan the person saw

See docs/LLD-solution-blueprints.md and docs/REFACTOR-blueprints.md.
"""

from collections import Counter

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.security import HTTPBearer

from src.blueprints.access import KitAccess, access_to, kit_with, visible_kits
from src.iam.dependencies import get_principal
from src.iam.principal import Principal

from src.blueprints.kinds import kind_for
from src.blueprints.kits import Kit, KitError, KitNotFound, KitPlan, plan_kit_removal, plan_rollback
from src.blueprints.models import (
    ApplyKitPlanRequest,
    Deployment,
    DeploymentStatus,
    KitDetail,
    KitPlanResponse,
    KitResourceView,
    KitSummary,
    KitVersionView,
    RollbackRequest,
)
from src.blueprints.repository import DeploymentRepository
from src.blueprints.service import Blocked, Deployed, DeployOutcome, Invalid, RateLimited, apply_kit_plan

router = APIRouter(prefix="/kits", tags=["kits"], dependencies=[Depends(HTTPBearer())])


def _summary(kit: Kit, access: KitAccess = "owner") -> dict:
    return {
        **kit.model_dump(include={"kit_id", "title", "description", "current_version", "versions", "conversation_id",
                                  "account_id", "owner_id", "created_at", "updated_at"}),
        "status": kit.status.value,
        "counts": dict(Counter(resource.kind for resource in kit.resources.values())),
        "access": access,
    }


# A kit's versions apply as its owner, whoever applies them (`deploy_blueprint`, `apply_kit_plan`)
Readable = Annotated[Kit, Depends(kit_with("kits:Get"))]
RollingBack = Annotated[Kit, Depends(kit_with("kits:Rollback"))]
Removing = Annotated[Kit, Depends(kit_with("kits:Delete"))]


def _planned(plan: KitPlan) -> KitPlanResponse:
    return KitPlanResponse(
        ok=plan.plan.ok,
        plan_id=plan.plan_id if plan.plan.ok else None,
        steps=plan.plan.steps,
        blockers=plan.plan.blockers,
        removals=plan.plan.removals,
    )


def _kit_error(error: KitError) -> HTTPException:
    return HTTPException(status_code=404 if isinstance(error, KitNotFound) else 409, detail=str(error))


def _applied(outcome: DeployOutcome) -> Deployment:
    match outcome:
        case Invalid(issues=issues):
            raise HTTPException(status_code=409, detail="; ".join(issue.message for issue in issues))
        case Blocked(plan=plan):
            raise HTTPException(status_code=422, detail="; ".join(issue.message for issue in plan.blockers))
        case RateLimited(retry_after_seconds=retry_after):
            raise HTTPException(
                status_code=429,
                detail="You've applied a lot of blueprints in the last hour. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )
        case Deployed(deployment=deployment):
            return deployment
    raise AssertionError(outcome)


@router.get("", response_model=list[KitSummary])
async def list_kits(principal: Annotated[Principal, Depends(get_principal)]) -> list[KitSummary]:
    """The caller's kits, those shared with them, and (for admins) everyone else's."""
    return [KitSummary.model_validate(_summary(kit, access)) for kit, access in visible_kits(principal)]


@router.get("/{kit_id}", response_model=KitDetail)
async def get_kit(kit: Readable, principal: Annotated[Principal, Depends(get_principal)]) -> KitDetail:
    deployments = DeploymentRepository().list_for_kit(kit.account_id, kit.kit_id)
    current = next((d for d in deployments if d.deployment_id == kit.current_deployment_id), None)
    attributes = {name: resource.attributes for name, resource in (current.resources.items() if current else [])}
    resources = []
    for name, resource in kit.resources.items():
        path = kind_for(resource.kind).dashboard_path
        resources.append(KitResourceView(
            name=name,
            kind=resource.kind,
            id=resource.id,
            title=attributes.get(name, {}).get("name") or name,
            dashboard_path=path.format(id=resource.id) if path else "",
        ))
    history = [
        KitVersionView(
            version=d.version or 0,
            deployment_id=d.deployment_id,
            action=d.action,
            status=d.status,
            current=d.deployment_id == kit.current_deployment_id,
            rolled_back_to=d.rolled_back_to,
            steps=d.steps,
            removed=d.removed,
            error=d.error,
            created_at=d.created_at,
        )
        for d in deployments
        if d.version is not None and d.status != DeploymentStatus.FAILED
    ]
    summary = _summary(kit, access_to(principal, kit) or "admin")
    return KitDetail.model_validate({**summary, "resources": resources, "history": history})


@router.post("/{kit_id}/rollback/plan", response_model=KitPlanResponse)
async def plan_kit_rollback(kit: RollingBack, body: RollbackRequest) -> KitPlanResponse:
    try:
        return _planned(plan_rollback(kit.account_id, kit.kit_id, body.version))
    except KitError as e:
        raise _kit_error(e) from e


@router.post("/{kit_id}/rollback", response_model=Deployment)
async def rollback_kit(kit: RollingBack, body: ApplyKitPlanRequest, background_tasks: BackgroundTasks) -> Deployment:
    if body.version is None:
        raise HTTPException(status_code=422, detail="Say which version to go back to.")
    try:
        planned = plan_rollback(kit.account_id, kit.kit_id, body.version)
    except KitError as e:
        raise _kit_error(e) from e
    return _applied(apply_kit_plan(planned, kit.account_id, kit.kit_id, body.plan_id, background_tasks))


@router.post("/{kit_id}/removal/plan", response_model=KitPlanResponse)
async def plan_removal(kit: Removing) -> KitPlanResponse:
    try:
        return _planned(plan_kit_removal(kit.account_id, kit.kit_id))
    except KitError as e:
        raise _kit_error(e) from e


@router.post("/{kit_id}/remove", response_model=Deployment)
async def remove_kit(kit: Removing, body: ApplyKitPlanRequest) -> Deployment:
    try:
        planned = plan_kit_removal(kit.account_id, kit.kit_id)
    except KitError as e:
        raise _kit_error(e) from e
    return _applied(apply_kit_plan(planned, kit.account_id, kit.kit_id, body.plan_id))
