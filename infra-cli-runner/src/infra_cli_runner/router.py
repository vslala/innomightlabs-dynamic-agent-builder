from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from src.infra_cli_runner.models import (
    CommandRequest,
    CommandResponse,
    FileSystemActionRequest,
    FileSystemActionResponse,
    PythonExecutionRequest,
    PythonExecutionResponse,
)
from src.infra_cli_runner.filesystem import FileSystemService, get_file_system_service
from src.infra_cli_runner.service import (
    CliRunnerService,
    CommandExecutionError,
    get_cli_runner_service,
)


router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/v1/commands", response_model=CommandResponse)
async def run_command(
    request: CommandRequest,
    service: Annotated[CliRunnerService, Depends(get_cli_runner_service)],
    authorization: str | None = Header(default=None),
) -> CommandResponse:
    token = _bearer_token(authorization)
    try:
        service.validate_token(token)
        return await service.run(request)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except CommandExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/v1/python/executions", response_model=PythonExecutionResponse)
async def run_python(
    request: PythonExecutionRequest,
    service: Annotated[CliRunnerService, Depends(get_cli_runner_service)],
    authorization: str | None = Header(default=None),
) -> PythonExecutionResponse:
    token = _bearer_token(authorization)
    try:
        service.validate_token(token)
        return await service.run_python(request)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except CommandExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/v1/filesystem/actions", response_model=FileSystemActionResponse)
async def run_filesystem_action(
    request: FileSystemActionRequest,
    service: Annotated[FileSystemService, Depends(get_file_system_service)],
    runner_service: Annotated[CliRunnerService, Depends(get_cli_runner_service)],
    authorization: str | None = Header(default=None),
) -> FileSystemActionResponse:
    token = _bearer_token(authorization)
    try:
        runner_service.validate_token(token)
        return service.execute(request)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except CommandExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def _bearer_token(authorization: str | None) -> str:
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return authorization[len(prefix):].strip()
