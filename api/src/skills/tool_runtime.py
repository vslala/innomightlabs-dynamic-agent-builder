"""Skill tool runtime: tool schema expansion + tool call execution.

This is the bridge between:
- Tools declared in tenant skill manifests
and
- Native executors (currently: HTTP executor)

Workflow:
- Resolve loaded skills (from core memory block [loaded_skills]) -> skill definitions (DDB)
- Load manifest.json from artifact store (S3 or local)
- Expose each manifest tool as an LLM tool schema (name/description/parameters)
- When LLM calls a tool, dispatch to executor based on tool definition

MVP supports only executor="http".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from src.skills.models import SkillDefinition, SkillManifest, SkillToolDefinition
from src.skills.repository import SkillsRepository
from src.skills.store import SkillsStore
from src.tools.http_executor import HttpExecutor, HttpExecutorError


@dataclass
class ResolvedTool:
    skill: SkillDefinition
    manifest: SkillManifest
    tool_def: SkillToolDefinition


class SkillToolRuntime:
    def __init__(
        self,
        repo: Optional[SkillsRepository] = None,
        store: Optional[SkillsStore] = None,
        http_executor: Optional[HttpExecutor] = None,
    ):
        self.repo = repo or SkillsRepository()
        self.store = store or __import__("src.skills.store", fromlist=["get_skills_store"]).get_skills_store()
        self.http = http_executor or HttpExecutor()

    def _tool_schema_from_tool_def(self, tool_def: SkillToolDefinition) -> dict[str, Any]:
        # Only expose OpenAI-compatible schema fields to the model.
        return {
            "name": tool_def.name,
            "description": tool_def.description,
            "parameters": tool_def.parameters,
        }

    def build_llm_tools_for_skill(self, manifest: SkillManifest) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for t in manifest.tools or []:
            tools.append(self._tool_schema_from_tool_def(t))
        return tools

    def load_manifest_for_skill(self, skill: SkillDefinition) -> SkillManifest:
        manifest_text = self.store.read_text(skill.s3_manifest_key)
        return SkillManifest.model_validate_json(manifest_text)

    def resolve_loaded_tool(
        self,
        *,
        owner_email: str,
        loaded_skills: list[dict[str, Any]],
        tool_name: str,
    ) -> Optional[ResolvedTool]:
        # loaded_skills records contain skill_id + version
        for rec in loaded_skills:
            if not isinstance(rec, dict):
                continue
            skill_id = str(rec.get("skill_id", "") or "").strip()
            version = str(rec.get("version", "") or "").strip()
            if not skill_id or not version:
                continue

            skill = self.repo.get(owner_email, skill_id, version)
            if not skill:
                continue

            manifest = self.load_manifest_for_skill(skill)
            for t in manifest.tools or []:
                if t.name == tool_name:
                    return ResolvedTool(skill=skill, manifest=manifest, tool_def=t)

        return None

    def _render_template_obj(self, obj: Any, args: dict[str, Any]) -> Any:
        """Render a template object replacing {{var}} in strings.

        This is intentionally minimal (no expressions).
        """
        if isinstance(obj, str):
            out = obj
            for k, v in args.items():
                out = out.replace("{{" + str(k) + "}}", str(v))
            return out
        if isinstance(obj, dict):
            return {k: self._render_template_obj(v, args) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._render_template_obj(v, args) for v in obj]
        return obj

    async def execute_tool(self, resolved: ResolvedTool, args: dict[str, Any]) -> str:
        tool_def = resolved.tool_def
        executor = tool_def.executor.value

        if executor != "http":
            return json.dumps({"ok": False, "error": f"Unsupported executor '{executor}'"}, ensure_ascii=False)

        assert tool_def.http is not None
        method = tool_def.http.method
        url = self._render_template_obj(tool_def.http.url, args)
        headers = self._render_template_obj(tool_def.http.headers, args)
        query = self._render_template_obj(tool_def.http.query, args)

        # Body can come from tool call args OR template; template wins if provided
        json_body = tool_def.http.json_body
        if json_body is None:
            json_body = args.get("json_body")
        json_body = self._render_template_obj(json_body, args)

        text_body = tool_def.http.text_body
        if text_body is None:
            text_body = args.get("text_body")
        text_body = self._render_template_obj(text_body, args)

        try:
            res = await self.http.request(
                method,
                url=url,
                headers=headers,
                query=query,
                json_body=json_body,
                text_body=text_body,
            )
            return res.to_json()
        except HttpExecutorError as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
