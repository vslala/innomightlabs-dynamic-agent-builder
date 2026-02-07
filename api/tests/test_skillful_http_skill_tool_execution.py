import json

import httpx
import pytest

from src.skills.models import SkillManifest
from src.skills.tool_runtime import SkillToolRuntime
from src.skills.local_store import LocalSkillsStore
from src.skills.repository import SkillsRepository
from src.tools.http_executor import HttpExecutor


@pytest.mark.asyncio
async def test_skill_tool_runtime_executes_http_tool_from_manifest(tmp_path, monkeypatch, dynamodb_table):
    # Use local store root
    root = tmp_path / "skills"
    store = LocalSkillsStore(root_dir=str(root))

    # Upload a manifest-based skill to local store and insert definition into DynamoDB
    manifest = SkillManifest(
        skill_id="demo",
        name="Demo",
        version="1.0.0",
        description="demo",
        allowed_hosts=["example.com"],
        tools=[
            {
                "name": "demo_get",
                "description": "Fetch demo",
                "parameters": {
                    "type": "object",
                    "properties": {"q": {"type": "string"}},
                    "required": ["q"],
                },
                "executor": "http",
                "http": {
                    "method": "GET",
                    "url": "https://example.com/hello",
                    "query": {"q": "{{q}}"},
                },
            }
        ],
    )

    artifact = store.upload_skill_manifest(owner_email="owner@example.com", manifest=manifest, skill_md="# demo")

    repo = SkillsRepository()
    from src.skills.models import SkillDefinition, SkillStatus

    repo.upsert(
        SkillDefinition(
            owner_email="owner@example.com",
            skill_id=manifest.skill_id,
            version=manifest.version,
            name=manifest.name,
            description=manifest.description,
            status=SkillStatus.ACTIVE,
            s3_zip_key=artifact.zip_key,
            s3_manifest_key=artifact.manifest_key,
            s3_skill_md_key=artifact.skill_md_key,
        )
    )

    # Mock HTTP
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.host == "example.com"
        assert req.url.params.get("q") == "test"
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        http_exec = HttpExecutor(client=client, allowed_hosts=["example.com"])
        runtime = SkillToolRuntime(repo=repo, store=store, http_executor=http_exec)

        loaded = [{"skill_id": "demo", "version": "1.0.0"}]
        resolved = runtime.resolve_loaded_tool(owner_email="owner@example.com", loaded_skills=loaded, tool_name="demo_get")
        assert resolved is not None

        out = await runtime.execute_tool(resolved, {"q": "test"})
        payload = json.loads(out)
        assert payload["ok"] is True
        assert payload["status_code"] == 200
