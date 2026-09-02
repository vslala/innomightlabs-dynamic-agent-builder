from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.skills.python_code_execution import actions, client
from src.skills.python_code_execution.models import RunScriptRequest
from src.skills.registry import SkillRegistry
from src.skills.workspaces import workspace_id_from_context


RUNTIME_CONTEXT = {
    "owner_email": "owner@example.com",
    "installed_skill_id": "python_code_execution",
    "conversation_id": "conv_123",
    "user_message_id": "msg_123",
}


def runner_response(*, ok: bool = True, timed_out: bool = False) -> dict[str, Any]:
    status = "succeeded" if ok else ("timed_out" if timed_out else "failed")
    exit_code = 0 if ok else (-15 if timed_out else 1)
    return {
        "ok": ok,
        "request_id": "msg_123",
        "exit_code": exit_code,
        "stdout": "script output\n" if ok else "",
        "stderr": "" if ok else "script failed\n",
        "duration_ms": 123,
        "stdout_truncated": False,
        "stderr_truncated": False,
        "timed_out": timed_out,
        "failed_command_index": None if ok else 1,
        "commands": [
            {
                "index": 0,
                "operation": "create_environment",
                "status": "succeeded",
                "exit_code": 0,
            },
            {
                "index": 1,
                "operation": "run_script",
                "status": status,
                "exit_code": exit_code,
                "stdout": "script output\n" if ok else "",
                "stderr": "" if ok else "script failed\n",
                "timed_out": timed_out,
            },
        ],
    }


def test_manifest_loads_without_install_config_and_disables_automations() -> None:
    loaded = SkillRegistry(Path("src/skills")).get("python_code_execution")

    assert loaded is not None
    assert loaded.manifest.namespace == "development.python"
    assert loaded.manifest.form == []
    assert loaded.manifest.automation.enabled is False
    assert [action.name for action in loaded.manifest.actions] == ["run_script"]
    assert loaded.manifest.actions[0].automation.enabled is False


def test_skill_installs_without_configuration(test_client, auth_headers) -> None:
    from tests.mock_data import TEST_USER_EMAIL

    agent = AgentRepository().save(
        Agent(
            agent_name="Python Execution Skill Test Agent",
            agent_architecture="krishna-memgpt",
            agent_provider="Bedrock",
            agent_model="claude-3-7-sonnet",
            agent_persona="Helpful",
            created_by=TEST_USER_EMAIL,
        )
    )

    response = test_client.post(
        f"/agents/{agent.agent_id}/skills?skill_id=python_code_execution",
        headers=auth_headers,
        json={"config": {}},
    )

    assert response.status_code == 201
    assert response.json()["skill_id"] == "python_code_execution"
    assert response.json()["config"] == {}


def test_request_defaults_to_sixty_seconds_and_builds_restricted_commands() -> None:
    without_requirements = RunScriptRequest.model_validate({"script": "print('ok')"})
    with_requirements = RunScriptRequest.model_validate(
        {
            "script": "import httpx",
            "requirements_txt": "httpx==0.28.1",
            "args": ["one"],
        }
    )

    assert without_requirements.timeout_seconds == 60
    assert without_requirements.runner_commands() == [
        {"operation": "run_script", "args": []}
    ]
    assert with_requirements.runner_commands() == [
        {"operation": "install_requirements"},
        {"operation": "run_script", "args": ["one"]},
    ]


def test_request_rejects_empty_script_null_args_and_runner_controls() -> None:
    with pytest.raises(ValidationError, match="script must not be empty"):
        RunScriptRequest.model_validate({"script": "  "})
    with pytest.raises(ValidationError, match="null bytes"):
        RunScriptRequest.model_validate({"script": "print('ok')", "args": ["bad\x00arg"]})
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RunScriptRequest.model_validate({"script": "print('ok')", "working_directory": "/tmp"})


@pytest.mark.asyncio
async def test_run_script_calls_runner_with_uv_environment_flow(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self) -> dict[str, Any]:
            return runner_response()

    class FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            captured["httpx_init"] = kwargs

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> FakeResponse:
            captured["url"] = url
            captured["payload"] = json
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(client.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(client.settings, "cli_runner_base_url", "http://runner.local")
    monkeypatch.setattr(client.settings, "cli_runner_shared_token", "runner-token")
    monkeypatch.setattr(client.settings, "cli_runner_timeout_seconds", 30)

    result = await actions.run_script(
        {
            "script": "import httpx\nprint(httpx.__version__)",
            "requirements_txt": "httpx==0.28.1",
            "args": ["one"],
        },
        {},
        RUNTIME_CONTEXT,
    )

    assert result["ok"] is True
    assert result["execution_status"] == "succeeded"
    assert result["stdout"] == "script output\n"
    assert captured["url"] == "http://runner.local/v1/python/executions"
    assert captured["headers"] == {"Authorization": "Bearer runner-token"}
    assert captured["payload"] == {
        "request_id": "msg_123",
        "script": "import httpx\nprint(httpx.__version__)",
        "requirements": "httpx==0.28.1",
        "commands": [
            {"operation": "install_requirements"},
            {"operation": "run_script", "args": ["one"]},
        ],
        "timeout_seconds": 60,
        "max_stdout_bytes": 16 * 1024,
        "max_stderr_bytes": 8 * 1024,
        "workspace_id": workspace_id_from_context(RUNTIME_CONTEXT),
    }
    assert captured["httpx_init"]["timeout"].read == 65


@pytest.mark.asyncio
async def test_user_code_failure_is_returned_as_structured_result(monkeypatch) -> None:
    class FakeRunnerClient:
        async def run_script(self, request: RunScriptRequest, context: dict[str, Any]):
            del request, context
            return client.RunnerExecutionResponse.model_validate(runner_response(ok=False))

    monkeypatch.setattr(actions, "get_python_runner_client", lambda: FakeRunnerClient())

    result = await actions.run_script({"script": "raise ValueError('no')"}, {}, RUNTIME_CONTEXT)

    assert result["ok"] is False
    assert result["execution_status"] == "failed"
    assert result["exit_code"] == 1
    assert result["failed_command_index"] == 1
    assert result["commands"][1]["status"] == "failed"


@pytest.mark.asyncio
async def test_runner_http_failure_raises_bounded_runtime_error(monkeypatch) -> None:
    class FakeResponse:
        status_code = 503
        text = "runner unavailable"

    class FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, *args: Any, **kwargs: Any) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(client.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(client.settings, "cli_runner_base_url", "http://runner.local")
    monkeypatch.setattr(client.settings, "cli_runner_shared_token", "runner-token")

    with pytest.raises(RuntimeError, match="HTTP 503 runner unavailable"):
        await actions.run_script({"script": "print('ok')"}, {}, RUNTIME_CONTEXT)


@pytest.mark.asyncio
async def test_runner_network_failure_is_runtime_error(monkeypatch) -> None:
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

    with pytest.raises(RuntimeError, match="Python runner request failed"):
        await actions.run_script({"script": "print('ok')"}, {}, RUNTIME_CONTEXT)
