from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.skills.file_system import actions, client
from src.skills.file_system.models import FileSystemResult
from src.skills.registry import SkillRegistry
from src.skills.workspaces import workspace_id_from_context


RUNTIME_CONTEXT = {
    "owner_email": "owner@example.com",
    "actor_email": "actor@example.com",
    "agent_id": "agent_123",
    "installed_skill_id": "file_system",
    "conversation_id": "conv_123",
    "user_message_id": "msg_123",
}


def test_manifest_exposes_complete_compact_action_surface() -> None:
    loaded = SkillRegistry(Path("src/skills")).get("file_system")

    assert loaded is not None
    assert loaded.manifest.automation.enabled is False
    assert [action.name for action in loaded.manifest.actions] == [
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
    assert all(action.input_schema.get("additionalProperties") is False for action in loaded.manifest.actions)


def test_workspace_id_is_stable_opaque_and_scoped_to_conversation() -> None:
    first = workspace_id_from_context(RUNTIME_CONTEXT)
    second = workspace_id_from_context(dict(RUNTIME_CONTEXT))
    other = workspace_id_from_context({**RUNTIME_CONTEXT, "conversation_id": "conv_other"})

    assert first == second
    assert first != other
    assert len(first) == 48
    assert "owner" not in first


@pytest.mark.asyncio
async def test_client_calls_sidecar_with_workspace_and_no_approval_contract(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self) -> dict[str, Any]:
            return {
                "status": "success",
                "payload": {"path": "report.txt", "deleted": True},
                "error_code": None,
                "message": None,
                "next_cursor": None,
            }

    class FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            captured["init"] = kwargs

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> FakeResponse:
            captured.update(url=url, payload=json, headers=headers)
            return FakeResponse()

    monkeypatch.setattr(client.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(client.settings, "cli_runner_base_url", "http://runner.local")
    monkeypatch.setattr(client.settings, "cli_runner_shared_token", "runner-token")
    monkeypatch.setattr(client.settings, "cli_runner_timeout_seconds", 30)

    result = await actions.delete(
        {"path": "report.txt", "recursive": False},
        {},
        RUNTIME_CONTEXT,
    )

    assert result["status"] == "success"
    assert captured["url"] == "http://runner.local/v1/filesystem/actions"
    assert captured["headers"] == {"Authorization": "Bearer runner-token"}
    assert captured["payload"]["workspace_id"] == workspace_id_from_context(RUNTIME_CONTEXT)
    assert "approved" not in captured["payload"]


@pytest.mark.asyncio
async def test_action_is_dispatched_and_audited_without_policy_enforcement(monkeypatch, caplog) -> None:
    calls: list[dict[str, Any]] = []

    class FakeRunnerClient:
        async def execute(self, **kwargs: Any) -> FileSystemResult:
            calls.append(kwargs)
            return FileSystemResult(status="success", payload={"deleted": True})

    monkeypatch.setattr(actions, "get_file_system_runner_client", lambda: FakeRunnerClient())
    with caplog.at_level(logging.INFO, logger=actions.__name__):
        result = await actions.delete({"path": "report.txt"}, {}, RUNTIME_CONTEXT)

    assert result["status"] == "success"
    assert "approved" not in calls[0]
    audit = next(record.filesystem_audit for record in caplog.records if hasattr(record, "filesystem_audit"))
    assert audit["action"] == "delete"
    assert audit["paths"] == ["report.txt"]
    assert audit["actor"] == "actor@example.com"
    assert audit["policy_decision"] == "not_enforced"
    assert audit["status"] == "success"


@pytest.mark.asyncio
async def test_client_network_failure_is_bounded_runtime_error(monkeypatch) -> None:
    class FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, *args: Any, **kwargs: Any) -> Any:
            raise httpx.ConnectError("connection failed")

    monkeypatch.setattr(client.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(client.settings, "cli_runner_base_url", "http://runner.local")
    monkeypatch.setattr(client.settings, "cli_runner_shared_token", "runner-token")

    with pytest.raises(RuntimeError, match="Filesystem runner request failed"):
        await actions.stat({"path": "report.txt"}, {}, RUNTIME_CONTEXT)
