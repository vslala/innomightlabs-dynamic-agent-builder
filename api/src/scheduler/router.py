"""Scheduler API router."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer

from src.scheduler.models import (
    CreateScheduleRequest,
    ScheduleResponse,
    ScheduleRunResponse,
    UpdateScheduleRequest,
)
from src.scheduler.repository import SchedulerRepository
from src.scheduler.service import SchedulerService, SchedulerValidationError

security = HTTPBearer()

router = APIRouter(prefix="/schedules", tags=["schedules"], dependencies=[Depends(security)])


def get_scheduler_repository() -> SchedulerRepository:
    return SchedulerRepository()


def get_scheduler_service(
    repository: Annotated[SchedulerRepository, Depends(get_scheduler_repository)],
) -> SchedulerService:
    return SchedulerService(repository=repository)


@router.get("", response_model=list[ScheduleResponse])
async def list_schedules(
    request: Request,
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
) -> list[ScheduleResponse]:
    return [schedule.to_response() for schedule in service.list_schedules(request.state.user_email)]


@router.post("", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    request: Request,
    body: CreateScheduleRequest,
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
) -> ScheduleResponse:
    try:
        schedule = service.create_schedule(body, request.state.user_email, request.state.user_email)
        return schedule.to_response()
    except SchedulerValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    request: Request,
    schedule_id: str,
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
) -> ScheduleResponse:
    try:
        return service.get_schedule(schedule_id, request.state.user_email).to_response()
    except SchedulerValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    request: Request,
    schedule_id: str,
    body: UpdateScheduleRequest,
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
) -> ScheduleResponse:
    try:
        return service.update_schedule(schedule_id, body, request.state.user_email).to_response()
    except SchedulerValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{schedule_id}/pause", response_model=ScheduleResponse)
async def pause_schedule(
    request: Request,
    schedule_id: str,
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
) -> ScheduleResponse:
    try:
        return service.pause_schedule(schedule_id, request.state.user_email).to_response()
    except SchedulerValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{schedule_id}/resume", response_model=ScheduleResponse)
async def resume_schedule(
    request: Request,
    schedule_id: str,
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
) -> ScheduleResponse:
    try:
        return service.resume_schedule(schedule_id, request.state.user_email).to_response()
    except SchedulerValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    request: Request,
    schedule_id: str,
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
) -> None:
    try:
        service.delete_schedule(schedule_id, request.state.user_email)
    except SchedulerValidationError:
        return None


@router.get("/{schedule_id}/runs", response_model=list[ScheduleRunResponse])
async def list_schedule_runs(
    request: Request,
    schedule_id: str,
    repository: Annotated[SchedulerRepository, Depends(get_scheduler_repository)],
    service: Annotated[SchedulerService, Depends(get_scheduler_service)],
) -> list[ScheduleRunResponse]:
    try:
        service.get_schedule(schedule_id, request.state.user_email)
    except SchedulerValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [run.to_response() for run in repository.list_runs(schedule_id)]
