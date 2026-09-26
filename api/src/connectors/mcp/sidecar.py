from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from src.config import settings
from src.connectors.mcp.client import MCPClientError
from src.connectors.mcp.models import MCPRuntimeStatusResponse, MCPStdioPackageResponse
from src.connectors.mcp.resolved import StdioTarget

log = logging.getLogger(__name__)

# Seconds the sidecar waits for a starting server before answering ensure; its own maximum is 60.
HTTP_TIMEOUT_GRACE_SECONDS = 10


class StdioMCPSidecarClient:
    """The API's view of hosted stdio servers on infra-cli-runner."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    def endpoint_url(self, server_id: str) -> str:
        return f"{self._base_url()}/v1/mcp/servers/{server_id}/mcp"

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}"}

    async def packages(self) -> list[MCPStdioPackageResponse]:
        response = await self._request("GET", "/v1/mcp/packages")
        return [MCPStdioPackageResponse.model_validate(item) for item in response.json()]

    async def ensure(self, server_id: str, target: StdioTarget, *, wait_seconds: int) -> MCPRuntimeStatusResponse:
        payload = {
            "spec": {
                "package": target.package,
                "args": list(target.args),
                "env": target.env,
                "files": target.files,
            },
            "wait_seconds": wait_seconds,
        }
        response = await self._request(
            "PUT",
            f"/v1/mcp/servers/{server_id}",
            json=payload,
            timeout=wait_seconds + HTTP_TIMEOUT_GRACE_SECONDS,
        )
        return MCPRuntimeStatusResponse.model_validate(response.json())

    async def status(self, server_id: str) -> Optional[MCPRuntimeStatusResponse]:
        response = await self._request("GET", f"/v1/mcp/servers/{server_id}", allow_not_found=True)
        if response.status_code == 404:
            return None
        return MCPRuntimeStatusResponse.model_validate(response.json())

    async def delete(self, server_id: str) -> None:
        await self._request("DELETE", f"/v1/mcp/servers/{server_id}")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        timeout: float | None = None,
        allow_not_found: bool = False,
    ) -> httpx.Response:
        url = f"{self._base_url()}{path}"
        request_timeout = httpx.Timeout(timeout or settings.cli_runner_timeout_seconds, connect=5)
        try:
            async with httpx.AsyncClient(timeout=request_timeout, transport=self.transport) as client:
                response = await client.request(method, url, json=json, headers=self.auth_headers())
        except httpx.HTTPError as exc:
            log.warning("Hosted MCP runtime request failed method=%s path=%s error=%s", method, path, exc)
            raise MCPClientError(f"Hosted MCP runtime is unavailable: {exc}") from exc

        if allow_not_found and response.status_code == 404:
            return response
        if response.is_error:
            detail = _detail(response)
            log.warning(
                "Hosted MCP runtime error method=%s path=%s status=%s detail=%s",
                method,
                path,
                response.status_code,
                detail,
            )
            raise MCPClientError(f"Hosted MCP runtime returned HTTP {response.status_code}: {detail}")
        return response

    def _base_url(self) -> str:
        if not settings.cli_runner_base_url:
            raise MCPClientError("Hosted MCP runtime is not configured. Set CLI_RUNNER_BASE_URL.")
        return settings.cli_runner_base_url.rstrip("/")

    def _token(self) -> str:
        if not settings.cli_runner_shared_token:
            raise MCPClientError("Hosted MCP runtime is not configured. Set CLI_RUNNER_SHARED_TOKEN.")
        return settings.cli_runner_shared_token


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:500]
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])[:500]
    return str(body)[:500]
