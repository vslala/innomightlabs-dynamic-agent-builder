import json

import httpx
import pytest

from src.crypto import decrypt
from src.skills.local_store import LocalSkillsStore
from src.skills.models import SkillDefinition, SkillManifest, SkillStatus
from src.skills.repository import SkillsRepository
from src.skills.secrets_repository import SkillSecretsRepository
from src.skills.tool_runtime import SkillToolRuntime
from src.tools.http_executor import HttpExecutor


@pytest.mark.asyncio
async def test_skill_secret_placeholder_injects_into_headers(tmp_path, dynamodb_table):
    # Local store
    store = LocalSkillsStore(root_dir=str(tmp_path / "skills"))

    manifest = SkillManifest(
        skill_id="demo",
        name="Demo",
        version="1.0.0",
        description="",
        allowed_hosts=["example.com"],
        tools=[
            {
                "name": "call",
                "description": "",
                "parameters": {"type": "object", "properties": {}},
                "executor": "http",
                "http": {
                    "method": "GET",
                    "url": "https://example.com/hello",
                    "headers": {"Authorization": "Bearer {{secret:wp_token}}"},
                },
            }
        ],
    )

    artifact = store.upload_skill_manifest(owner_email="owner@example.com", manifest=manifest, skill_md="#")

    repo = SkillsRepository()
    repo.upsert(
        SkillDefinition(
            owner_email="owner@example.com",
            skill_id="demo",
            version="1.0.0",
            name="Demo",
            description="",
            status=SkillStatus.ACTIVE,
            s3_zip_key=artifact.zip_key,
            s3_manifest_key=artifact.manifest_key,
            s3_skill_md_key=artifact.skill_md_key,
        )
    )

    secrets_repo = SkillSecretsRepository()
    saved = secrets_repo.upsert_plaintext(
        owner_email="owner@example.com",
        skill_id="demo",
        name="wp_token",
        value="SECRET123",
    )
    assert decrypt(saved.encrypted_value) == "SECRET123"

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers.get("Authorization") == "Bearer SECRET123"
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        http_exec = HttpExecutor(client=client, allowed_hosts=["example.com"])
        runtime = SkillToolRuntime(repo=repo, store=store, http_executor=http_exec, secrets_repo=secrets_repo)

        loaded = [{"skill_id": "demo", "version": "1.0.0"}]
        resolved = runtime.resolve_loaded_tool(owner_email="owner@example.com", loaded_skills=loaded, tool_name="call")
        assert resolved is not None

        out = await runtime.execute_tool(resolved, {})
        payload = json.loads(out)
        assert payload["ok"] is True
