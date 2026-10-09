"""
Solution blueprints: validate, plan and apply YAML descriptions of a solution.

Endpoints:
    GET  /blueprints/schema/v2.json          JSON Schema (public, for editors)
    GET  /blueprints/reference               Markdown reference (public)
    GET  /blueprints/catalog                 Kinds and skills, compact, for models
    GET  /blueprints/examples/{name}         An example blueprint
    POST /blueprints/validate                Issues, and the params form when valid
    POST /blueprints/plan                    Steps and blockers; no side effects
    POST /blueprints/deployments             Apply
    GET  /blueprints/deployments             List
    GET  /blueprints/deployments/{id}        One deployment

See docs/LLD-solution-blueprints.md.
"""

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import HTTPBearer

from src.blueprints.catalog import blueprint_json_schema, catalog, example_yaml, params_form, reference_markdown
from src.blueprints.issues import BlueprintInvalid
from src.blueprints.models import (
    BlueprintRequest,
    Deployment,
    DeploymentSummary,
    PlanResponse,
    ValidateResponse,
)
from src.blueprints.kits import KitError, KitNotFound, active_kit, declared, pin
from src.blueprints.planner import plan_blueprint
from src.blueprints.repository import DeploymentRepository
from src.blueprints.service import Blocked, Deployed, Invalid, RateLimited, deploy_blueprint
from src.blueprints.validator import validate_blueprint
from src.skills.registry import get_skill_registry
from src.skills.service import get_skill_service

log = logging.getLogger(__name__)

#: Paths open without sign-in, so editors can fetch the schema. Listed in auth PUBLIC_PATHS.
SCHEMA_PATH = "/blueprints/schema/v2.json"
REFERENCE_PATH = "/blueprints/reference"

public_router = APIRouter(prefix="/blueprints", tags=["blueprints"])
router = APIRouter(prefix="/blueprints", tags=["blueprints"], dependencies=[Depends(HTTPBearer())])


@public_router.get("/schema/v2.json")
async def get_schema(response: Response) -> dict[str, Any]:
    response.headers["ETag"] = f'"{get_skill_registry().version}"'
    return blueprint_json_schema()


@public_router.get("/reference", response_class=PlainTextResponse)
async def get_reference() -> str:
    return reference_markdown()


@router.get("/catalog")
async def get_catalog(request: Request) -> dict[str, Any]:
    ready = {item.skill_id: item.available and item.oauth_connected is not False
             for item in get_skill_service().list_catalog(request.state.user_email)}
    return catalog(ready=ready)


@router.get("/examples/{name}")
async def get_example(name: str) -> dict[str, str]:
    text = example_yaml(name)
    if text is None:
        raise HTTPException(status_code=404, detail="Example not found")
    return {"name": name, "yaml": text}


@router.post("/validate", response_model=ValidateResponse)
async def validate(body: BlueprintRequest) -> ValidateResponse:
    try:
        validated = validate_blueprint(body.yaml, body.params)
    except BlueprintInvalid as e:
        return ValidateResponse(valid=False, issues=e.issues)
    return ValidateResponse(valid=True, params_form=params_form(validated.blueprint).model_dump(exclude_none=True))


@router.post("/plan", response_model=PlanResponse)
async def plan(request: Request, body: BlueprintRequest) -> PlanResponse:
    try:
        validated = validate_blueprint(body.yaml, body.params or {})
    except BlueprintInvalid as e:
        return PlanResponse(ok=False, issues=e.issues)
    if not body.kit_id:
        result = plan_blueprint(validated, request.state.user_email)
        return PlanResponse(ok=result.ok, steps=result.steps, blockers=result.blockers)
    try:
        kit = active_kit(request.state.user_email, body.kit_id)
        validated = validate_blueprint(pin(body.yaml, kit), body.params or {})
        result = plan_blueprint(validated, request.state.user_email, declared(kit))
    except BlueprintInvalid as e:
        return PlanResponse(ok=False, issues=e.issues)
    except KitError as e:
        raise HTTPException(status_code=404 if isinstance(e, KitNotFound) else 409, detail=str(e)) from e
    return PlanResponse(ok=result.ok, steps=result.steps, blockers=result.blockers)


@router.post("/deployments", response_model=Deployment, status_code=status.HTTP_201_CREATED)
async def create_deployment(request: Request, body: BlueprintRequest, background_tasks: BackgroundTasks):
    outcome = deploy_blueprint(
        body.yaml, body.params or {}, request.state.user_email, background_tasks, kit_id=body.kit_id
    )
    match outcome:
        case Invalid(issues=issues):
            return JSONResponse(status_code=422, content=PlanResponse(ok=False, issues=issues).model_dump(mode="json"))
        case Blocked(plan=plan):
            return JSONResponse(
                status_code=422,
                content=PlanResponse(ok=False, steps=plan.steps, blockers=plan.blockers).model_dump(mode="json"),
            )
        case RateLimited(retry_after_seconds=retry_after):
            raise HTTPException(
                status_code=429,
                detail="You've applied a lot of blueprints in the last hour. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )
        case Deployed(deployment=deployment):
            return deployment


@router.get("/deployments", response_model=list[DeploymentSummary])
async def list_deployments(request: Request) -> list[DeploymentSummary]:
    return [
        DeploymentSummary.model_validate(deployment.model_dump())
        for deployment in DeploymentRepository().list_by_user(request.state.user_email)
    ]


@router.get("/deployments/{deployment_id}", response_model=Deployment)
async def get_deployment(request: Request, deployment_id: str) -> Deployment:
    deployment = DeploymentRepository().find_by_id(request.state.user_email, deployment_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return deployment
