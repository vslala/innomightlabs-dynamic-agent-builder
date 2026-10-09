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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.security import HTTPBearer

from src.blueprints.kinds import kind_for
from src.blueprints.kits import Kit, KitError, KitNotFound, KitPlan, KitRepository, plan_kit_removal, plan_rollback
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


def _summary(kit: Kit) -> dict:
    return {
        **kit.model_dump(include={"kit_id", "title", "description", "current_version", "versions", "conversation_id",
                                  "created_at", "updated_at"}),
        "status": kit.status.value,
        "counts": dict(Counter(resource.kind for resource in kit.resources.values())),
    }


def _kit(request: Request, kit_id: str) -> Kit:
    kit = KitRepository().find(request.state.user_email, kit_id)
    if kit is None:
        raise HTTPException(status_code=404, detail="Kit not found")
    return kit


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
async def list_kits(request: Request) -> list[KitSummary]:
    return [KitSummary.model_validate(_summary(kit)) for kit in KitRepository().list_by_user(request.state.user_email)]


@router.get("/{kit_id}", response_model=KitDetail)
async def get_kit(request: Request, kit_id: str) -> KitDetail:
    kit = _kit(request, kit_id)
    deployments = DeploymentRepository().list_for_kit(request.state.user_email, kit_id)
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
    return KitDetail.model_validate({**_summary(kit), "resources": resources, "history": history})


@router.post("/{kit_id}/rollback/plan", response_model=KitPlanResponse)
async def plan_kit_rollback(request: Request, kit_id: str, body: RollbackRequest) -> KitPlanResponse:
    try:
        return _planned(plan_rollback(request.state.user_email, kit_id, body.version))
    except KitError as e:
        raise _kit_error(e) from e


@router.post("/{kit_id}/rollback", response_model=Deployment)
async def rollback_kit(
    request: Request, kit_id: str, body: ApplyKitPlanRequest, background_tasks: BackgroundTasks
) -> Deployment:
    if body.version is None:
        raise HTTPException(status_code=422, detail="Say which version to go back to.")
    try:
        planned = plan_rollback(request.state.user_email, kit_id, body.version)
    except KitError as e:
        raise _kit_error(e) from e
    return _applied(apply_kit_plan(planned, request.state.user_email, kit_id, body.plan_id, background_tasks))


@router.post("/{kit_id}/removal/plan", response_model=KitPlanResponse)
async def plan_removal(request: Request, kit_id: str) -> KitPlanResponse:
    try:
        return _planned(plan_kit_removal(request.state.user_email, kit_id))
    except KitError as e:
        raise _kit_error(e) from e


@router.post("/{kit_id}/remove", response_model=Deployment)
async def remove_kit(request: Request, kit_id: str, body: ApplyKitPlanRequest) -> Deployment:
    try:
        planned = plan_kit_removal(request.state.user_email, kit_id)
    except KitError as e:
        raise _kit_error(e) from e
    return _applied(apply_kit_plan(planned, request.state.user_email, kit_id, body.plan_id))
