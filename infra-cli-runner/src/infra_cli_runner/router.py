from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Path, Response, status
from fastapi.responses import JSONResponse

from src.infra_cli_runner.models import (
    CommandRequest,
    CommandResponse,
    EnsureHostedMCPServerRequest,
    HostedMCPPackage,
    HostedMCPServerStatus,
    FileSystemActionRequest,
    FileSystemActionResponse,
    PythonExecutionRequest,
    PythonExecutionResponse,
)
from src.infra_cli_runner.filesystem import FileSystemService, get_file_system_service
from src.infra_cli_runner.mcp_servers import (
    PoolFullError,
    ServerNotRunningError,
    ServerRequestTimeout,
    StdioMCPServerPool,
    UnknownPackageError,
    get_mcp_server_pool,
)
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


ServerId = Annotated[str, Path(pattern=r"^[0-9a-f-]{36}$")]


def _authorize(runner_service: CliRunnerService, authorization: str | None) -> None:
    try:
        runner_service.validate_token(_bearer_token(authorization))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except CommandExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/v1/mcp/packages", response_model=list[HostedMCPPackage])
async def list_mcp_packages(
    runner_service: Annotated[CliRunnerService, Depends(get_cli_runner_service)],
    pool: Annotated[StdioMCPServerPool, Depends(get_mcp_server_pool)],
    authorization: str | None = Header(default=None),
) -> list[HostedMCPPackage]:
    _authorize(runner_service, authorization)
    return pool.list_packages()


@router.put("/v1/mcp/servers/{server_id}", response_model=HostedMCPServerStatus)
async def ensure_mcp_server(
    server_id: ServerId,
    request: EnsureHostedMCPServerRequest,
    runner_service: Annotated[CliRunnerService, Depends(get_cli_runner_service)],
    pool: Annotated[StdioMCPServerPool, Depends(get_mcp_server_pool)],
    authorization: str | None = Header(default=None),
) -> HostedMCPServerStatus:
    _authorize(runner_service, authorization)
    try:
        return await pool.ensure(server_id, request.spec, wait_seconds=request.wait_seconds)
    except UnknownPackageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PoolFullError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/v1/mcp/servers/{server_id}", response_model=HostedMCPServerStatus)
async def get_mcp_server(
    server_id: ServerId,
    runner_service: Annotated[CliRunnerService, Depends(get_cli_runner_service)],
    pool: Annotated[StdioMCPServerPool, Depends(get_mcp_server_pool)],
    authorization: str | None = Header(default=None),
) -> HostedMCPServerStatus:
    _authorize(runner_service, authorization)
    server_status = pool.status(server_id)
    if server_status is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server is not running")
    return server_status


@router.delete("/v1/mcp/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_server(
    server_id: ServerId,
    runner_service: Annotated[CliRunnerService, Depends(get_cli_runner_service)],
    pool: Annotated[StdioMCPServerPool, Depends(get_mcp_server_pool)],
    authorization: str | None = Header(default=None),
) -> Response:
    _authorize(runner_service, authorization)
    await pool.delete(server_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/v1/mcp/servers/{server_id}/mcp")
async def mcp_server_facade(
    server_id: ServerId,
    runner_service: Annotated[CliRunnerService, Depends(get_cli_runner_service)],
    pool: Annotated[StdioMCPServerPool, Depends(get_mcp_server_pool)],
    message: Any = Body(...),
    authorization: str | None = Header(default=None),
) -> Response:
    """Streamable HTTP, JSON responses only, no sessions: a stateless front for one stdio process."""
    _authorize(runner_service, authorization)
    if not isinstance(message, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="JSON-RPC batches are not supported")
    try:
        response = await pool.forward(server_id, message)
    except ServerNotRunningError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ServerRequestTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    if response is None:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    return JSONResponse(response)


def _bearer_token(authorization: str | None) -> str:
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return authorization[len(prefix):].strip()
