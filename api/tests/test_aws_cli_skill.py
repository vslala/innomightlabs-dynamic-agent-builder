from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped,unused-ignore]

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.crypto import decrypt
from src.skills.aws_cli import actions
from src.skills.aws_cli.models import AwsCliConfig, AwsCliReadRequest, parse_policy
from src.skills.registry import SkillRegistry


VALID_CONFIG = {
    "aws_access_key_id": "AKIATEST",
    "aws_secret_access_key": "secret",
    "aws_region": "us-east-1",
    "command_policy_yaml": """
aws:
  default_timeout_seconds: 30
  max_timeout_seconds: 120
  max_stdout_bytes: 65536
  max_stderr_bytes: 16384
  sts_duration_seconds: 900
  services:
    sts:
      read:
        - ["sts", "get-caller-identity"]
    s3:
      read:
        - ["s3api", "list-buckets"]
        - ["s3api", "list-objects-v2"]
""",
}

RUNTIME_CONTEXT = {
    "owner_email": "owner@example.com",
    "installed_skill_id": "aws_cli",
    "conversation_id": "conv_123",
    "user_message_id": "msg_123",
}


def test_manifest_loads_and_declares_secret_install_fields() -> None:
    loaded = SkillRegistry(Path("src/skills")).get("aws_cli")

    assert loaded is not None
    assert loaded.manifest.namespace == "infrastructure.aws"
    assert loaded.manifest.automation.enabled is False
    assert [action.name for action in loaded.manifest.actions] == ["run_read", "read_output_page"]

    secret_fields = {
        field.name
        for field in loaded.manifest.form
        if (field.attr or {}).get("secret") == "true"
    }
    assert secret_fields == {"aws_access_key_id", "aws_secret_access_key"}


def test_install_asks_for_aws_credentials_and_stores_them_as_secrets(
    test_client,
    auth_headers,
    dynamodb_table,
) -> None:
    from tests.mock_data import TEST_USER_EMAIL

    agent = AgentRepository().save(
        Agent(
            agent_name="AWS Skill Test Agent",
            agent_architecture="krishna-memgpt",
            agent_provider="Bedrock",
            agent_model="claude-3-7-sonnet",
            agent_persona="Helpful",
            created_by=TEST_USER_EMAIL,
        )
    )

    schema_resp = test_client.get("/skills/aws_cli/install-schema", headers=auth_headers)
    assert schema_resp.status_code == 200
    fields = {field["name"]: field for field in schema_resp.json()["form_inputs"]}
    assert fields["aws_access_key_id"]["input_type"] == "password"
    assert fields["aws_access_key_id"]["attr"]["secret"] == "true"
    assert fields["aws_secret_access_key"]["input_type"] == "password"
    assert fields["aws_secret_access_key"]["attr"]["secret"] == "true"
    assert "command_policy_yaml" in fields

    install_resp = test_client.post(
        f"/agents/{agent.agent_id}/skills?skill_id=aws_cli",
        headers=auth_headers,
        json={"config": VALID_CONFIG},
    )
    assert install_resp.status_code == 201
    installed = install_resp.json()
    assert installed["skill_id"] == "aws_cli"
    assert installed["secret_fields"] == ["aws_access_key_id", "aws_secret_access_key"]
    assert "aws_access_key_id" not in installed["config"]
    assert "aws_secret_access_key" not in installed["config"]
    assert installed["config"]["aws_region"] == "us-east-1"
    assert installed["config"]["command_policy_yaml"]

    raw = dynamodb_table.get_item(
        Key={"pk": f"Agent#{agent.agent_id}", "sk": "Skill#aws_cli"}
    )["Item"]
    assert "aws_access_key_id" not in raw["config"]
    assert "aws_secret_access_key" not in raw["config"]
    decrypted_secrets = json.loads(decrypt(raw["encrypted_secrets"]))
    assert decrypted_secrets == {
        "aws_access_key_id": "AKIATEST",
        "aws_secret_access_key": "secret",
    }


def test_default_policy_file_matches_install_form_default() -> None:
    manifest = yaml.safe_load(Path("src/skills/aws_cli/manifest.yml").read_text())
    policy_field = next(field for field in manifest["form"] if field["name"] == "command_policy_yaml")
    default_policy = Path("src/skills/aws_cli/default_policy.yml").read_text()

    assert yaml.safe_load(policy_field["value"]) == yaml.safe_load(default_policy)
    parse_policy(default_policy)


def test_policy_accepts_allowed_read_prefix_and_rejects_unknown_command() -> None:
    config = AwsCliConfig.model_validate(VALID_CONFIG)
    policy = parse_policy(config.command_policy_yaml)

    policy.validate_read_argv(["s3api", "list-buckets"])
    with pytest.raises(ValueError, match="not allowed"):
        policy.validate_read_argv(["s3api", "delete-object", "--bucket", "demo", "--key", "x"])


def test_request_rejects_shell_syntax() -> None:
    with pytest.raises(ValueError, match="shell"):
        AwsCliReadRequest.model_validate({"argv": ["s3api", "list-buckets", "|", "cat"]})


@pytest.mark.asyncio
async def test_run_read_uses_sts_temp_credentials_and_calls_runner(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeStsClient:
        def get_session_token(self, DurationSeconds: int) -> dict[str, Any]:
            captured["sts_duration"] = DurationSeconds
            return {
                "Credentials": {
                    "AccessKeyId": "TEMP_ACCESS",
                    "SecretAccessKey": "TEMP_SECRET",
                    "SessionToken": "TEMP_TOKEN",
                    "Expiration": datetime.now(timezone.utc),
                }
            }

    def fake_boto3_client(*args: Any, **kwargs: Any) -> FakeStsClient:
        captured["boto3_args"] = args
        captured["boto3_kwargs"] = kwargs
        return FakeStsClient()

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self) -> dict[str, Any]:
            return {
                "ok": True,
                "exit_code": 0,
                "stdout": '{"Buckets":[]}',
                "stderr": "",
                "duration_ms": 12,
                "stdout_truncated": False,
                "stderr_truncated": False,
            }

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

    monkeypatch.setattr(actions.boto3, "client", fake_boto3_client)
    monkeypatch.setattr(actions.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(actions.settings, "cli_runner_base_url", "http://runner.local")
    monkeypatch.setattr(actions.settings, "cli_runner_shared_token", "runner-token")
    monkeypatch.setattr(actions.settings, "cli_runner_timeout_seconds", 10)

    result = await actions.run_read(
        {"argv": ["s3api", "list-buckets"]},
        VALID_CONFIG,
        RUNTIME_CONTEXT,
    )

    assert result["ok"] is True
    assert result["json"] == {"Buckets": []}
    assert captured["sts_duration"] == 900
    assert captured["boto3_kwargs"]["aws_access_key_id"] == "AKIATEST"
    assert captured["payload"]["env"] == {
        "AWS_ACCESS_KEY_ID": "TEMP_ACCESS",
        "AWS_SECRET_ACCESS_KEY": "TEMP_SECRET",
        "AWS_SESSION_TOKEN": "TEMP_TOKEN",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_REGION": "us-east-1",
    }
    assert captured["headers"] == {"Authorization": "Bearer runner-token"}
    assert captured["url"] == "http://runner.local/v1/commands"


@pytest.mark.asyncio
async def test_run_read_returns_paged_output(monkeypatch) -> None:
    large_stdout = "x" * 2500

    async def fake_create_sts_session(*args: Any, **kwargs: Any) -> dict[str, str]:
        return {
            "AWS_ACCESS_KEY_ID": "TEMP_ACCESS",
            "AWS_SECRET_ACCESS_KEY": "TEMP_SECRET",
            "AWS_SESSION_TOKEN": "TEMP_TOKEN",
        }

    async def fake_call_runner(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "exit_code": 0,
            "stdout": large_stdout,
            "stderr": "",
            "duration_ms": 12,
            "stdout_truncated": False,
            "stderr_truncated": False,
        }

    monkeypatch.setattr(actions, "_create_sts_session", fake_create_sts_session)
    monkeypatch.setattr(actions, "_call_runner", fake_call_runner)

    result = await actions.run_read(
        {"argv": ["s3api", "list-buckets"], "page_size_chars": 1000},
        VALID_CONFIG,
        RUNTIME_CONTEXT,
    )

    assert result["has_more"] is True
    assert result["page"] == 1
    assert result["total_pages"] == 3
    assert len(result["content"]) == 1000

    page_2 = await actions.read_output_page(
        {"output_id": result["output_id"], "page": result["next_page"], "page_size_chars": 1000},
        {},
        RUNTIME_CONTEXT,
    )
    assert page_2["page"] == 2
    assert page_2["has_next"] is True
    assert len(page_2["content"]) == 1000
