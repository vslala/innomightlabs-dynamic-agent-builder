import json

import httpx
import pytest

from src.skills.local_store import LocalSkillsStore
from src.skills.models import SkillDefinition, SkillManifest, SkillStatus
from src.skills.repository import SkillsRepository
from src.skills.tool_runtime import SkillToolRuntime
from src.tools.http_executor import HttpExecutor


@pytest.mark.asyncio
async def test_unresolved_placeholders_are_pruned_from_query(tmp_path, dynamodb_table):
    store = LocalSkillsStore(root_dir=str(tmp_path / "skills"))

    manifest = SkillManifest(
        skill_id="demo",
        name="Demo",
        version="1.0.0",
        description="",
        allowed_hosts=["example.com"],
        tools=[
            {
                "name": "t",
                "description": "",
                "parameters": {
                    "type": "object",
                    "properties": {"q": {"type": "string"}},
                    "required": [],
                },
                "executor": "http",
                "http": {
                    "method": "GET",
                    "url": "https://example.com/hello",
                    "query": {"q": "{{q}}", "page": "{{page}}"},
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

    def handler(req: httpx.Request) -> httpx.Response:
        # q should be absent because unresolved (missing arg)
        assert "q" not in req.url.params
        # page should be absent because unresolved (missing arg)
        assert "page" not in req.url.params
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        http_exec = HttpExecutor(client=client, allowed_hosts=["example.com"])
        runtime = SkillToolRuntime(repo=repo, store=store, http_executor=http_exec)

        resolved = runtime.resolve_loaded_tool(
            owner_email="owner@example.com",
            loaded_skills=[{"skill_id": "demo", "version": "1.0.0"}],
            tool_name="t",
        )
        assert resolved is not None

        out = await runtime.execute_tool(resolved, {})
        payload = json.loads(out)
        assert payload["ok"] is True
