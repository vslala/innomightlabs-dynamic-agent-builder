"""Where an upload's bytes come from: what the agent sent, or a file in its workspace on the infra CLI runner.

A `workspace_path` means the file is on the runner; otherwise the content is in the request.
"""

from __future__ import annotations

import tempfile
from typing import Any, Protocol

import httpx

from src.config import settings
from src.skills.upload_file.content import SPOOL_BYTES, UploadContent
from src.skills.upload_file.models import UploadFileRequest
from src.skills.workspaces import workspace_id_from_context

CHUNK_BYTES = 1024 * 1024


class ContentSource(Protocol):
    def handles(self, request: UploadFileRequest) -> bool:
        ...

    async def load(self, request: UploadFileRequest, context: dict[str, Any], max_bytes: int) -> UploadContent:
        ...


class InlineContentSource:
    def handles(self, request: UploadFileRequest) -> bool:
        return request.workspace_path is None

    async def load(self, request: UploadFileRequest, context: dict[str, Any], max_bytes: int) -> UploadContent:
        del context, max_bytes  # the request model already capped what can be sent inline
        return UploadContent.from_bytes(request.to_body_bytes())


class WorkspaceFileSource:
    """Streams the file out of the conversation's workspace on the infra CLI runner."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    def handles(self, request: UploadFileRequest) -> bool:
        return request.workspace_path is not None

    async def load(self, request: UploadFileRequest, context: dict[str, Any], max_bytes: int) -> UploadContent:
        path = str(request.workspace_path)
        if not settings.cli_runner_base_url or not settings.cli_runner_shared_token:
            raise RuntimeError("CLI runner is not configured. Set CLI_RUNNER_BASE_URL and CLI_RUNNER_SHARED_TOKEN.")
        # The workspace comes from the run's own identity, so an agent can only upload from its own conversation.
        query = {"workspace_id": workspace_id_from_context(context), "path": path}
        headers = {"Authorization": f"Bearer {settings.cli_runner_shared_token}"}
        url = f"{settings.cli_runner_base_url.rstrip('/')}/v1/filesystem/files"
        file = tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0), transport=self._transport) as http:
                async with http.stream("GET", url, params=query, headers=headers) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        raise RuntimeError(_describe_failure(response, path))
                    size = int(response.headers.get("content-length") or 0)
                    if size > max_bytes:
                        raise ValueError(_too_large(path, max_bytes))
                    size = 0
                    async for chunk in response.aiter_bytes(CHUNK_BYTES):
                        size += len(chunk)
                        if size > max_bytes:
                            raise ValueError(_too_large(path, max_bytes))
                        file.write(chunk)
        except httpx.TimeoutException as exc:
            file.close()
            raise RuntimeError(f"Reading {path} from the workspace timed out.") from exc
        except httpx.HTTPError as exc:
            file.close()
            raise RuntimeError(f"Reading {path} from the workspace failed: the runner is unreachable.") from exc
        except BaseException:
            file.close()
            raise
        file.seek(0)
        return UploadContent(file=file, size=size)


SOURCES: list[ContentSource] = [WorkspaceFileSource(), InlineContentSource()]


def source_for(request: UploadFileRequest) -> ContentSource:
    return next(source for source in SOURCES if source.handles(request))


def _too_large(path: str, max_bytes: int) -> str:
    return f"{path} is larger than the {max_bytes // (1024 * 1024)} MB upload limit for this type of file"


def _describe_failure(response: httpx.Response, path: str) -> str:
    if response.status_code == 404:
        return f"{path} isn't in this conversation's workspace (or the runner is older than this skill). Check the path."
    if response.status_code in (401, 403):
        return "The runner rejected this service's credentials (a deployment problem, not something to retry)."
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    return f"The runner refused {path}: {str(detail or response.status_code)[:300]}"
