from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


FileSystemActionName = Literal[
    "list_dir",
    "stat",
    "search",
    "read_chunk",
    "write_file",
    "patch_file",
    "preview_diff",
    "mkdir",
    "copy",
    "move",
    "delete",
    "batch",
]


class FileSystemRunnerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(pattern=r"^[a-f0-9]{48}$")
    action: FileSystemActionName
    arguments: dict[str, Any] = Field(default_factory=dict)


class FileSystemResult(BaseModel):
    status: Literal["success", "error"]
    payload: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    message: str | None = None
    next_cursor: str | None = None
