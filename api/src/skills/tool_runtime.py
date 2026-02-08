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
import re

from src.crypto import decrypt
from src.skills.secrets_repository import SkillSecretsRepository
from src.tools.http_executor import HttpExecutor, HttpExecutorError


@dataclass
class ResolvedTool:
    skill: SkillDefinition
    manifest: SkillManifest
    tool_def: SkillToolDefinition


class SkillToolRuntime:
    SECRET_PATTERN = re.compile(r"\{\{secret:([a-zA-Z0-9_\-]+)\}\}")

    def __init__(
        self,
        repo: Optional[SkillsRepository] = None,
        store: Optional[SkillsStore] = None,
        http_executor: Optional[HttpExecutor] = None,
        secrets_repo: Optional[SkillSecretsRepository] = None,
    ):
        self.repo = repo or SkillsRepository()
        self.store = store or __import__("src.skills.store", fromlist=["get_skills_store"]).get_skills_store()
        self.http = http_executor or HttpExecutor()
        self.secrets_repo = secrets_repo or SkillSecretsRepository()

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

    def _inject_secrets(self, *, owner_email: str, skill_id: str, text: str) -> str:
        matches = list(self.SECRET_PATTERN.finditer(text))
        if not matches:
            return text

        # Load secrets once per execution
        secrets = {s.name: decrypt(s.encrypted_value) for s in self.secrets_repo.list_for_skill(owner_email, skill_id)}

        def repl(m: re.Match) -> str:
            key = m.group(1)
            if key not in secrets:
                raise ValueError(f"Missing secret '{key}' for skill '{skill_id}'")
            return str(secrets[key])

        return self.SECRET_PATTERN.sub(repl, text)

    def _render_template_obj(self, obj: Any, args: dict[str, Any], *, owner_email: str, skill_id: str) -> Any:
        """Render a template object replacing {{var}} and {{secret:name}} in strings.

        Robustness rules:
        - If a placeholder cannot be resolved (arg missing), return None.
        - If a rendered string still contains an unresolved {{...}} token, return None.
        """
        if isinstance(obj, str):
            out = obj
            for k, v in args.items():
                if v is None:
                    continue
                out = out.replace("{{" + str(k) + "}}", str(v))

            out = self._inject_secrets(owner_email=owner_email, skill_id=skill_id, text=out)

            # If any placeholders remain, treat as missing
            if "{{" in out and "}}" in out:
                return None

            # Treat empty strings as None for query/header pruning
            if out.strip() == "":
                return None

            return out

        if isinstance(obj, dict):
            return {k: self._render_template_obj(v, args, owner_email=owner_email, skill_id=skill_id) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._render_template_obj(v, args, owner_email=owner_email, skill_id=skill_id) for v in obj]
        return obj

    async def execute_tool(self, resolved: ResolvedTool, args: dict[str, Any]) -> str:
        tool_def = resolved.tool_def
        executor = tool_def.executor.value
        owner_email = resolved.skill.owner_email
        skill_id = resolved.skill.skill_id

        if executor != "http":
            return json.dumps({"ok": False, "error": f"Unsupported executor '{executor}'"}, ensure_ascii=False)

        assert tool_def.http is not None
        method = tool_def.http.method
        url = self._render_template_obj(tool_def.http.url, args, owner_email=owner_email, skill_id=skill_id)
        headers = self._render_template_obj(tool_def.http.headers, args, owner_email=owner_email, skill_id=skill_id)
        query = self._render_template_obj(tool_def.http.query, args, owner_email=owner_email, skill_id=skill_id)

        # Prune Nones from headers/query so we don't send unresolved placeholders.
        if isinstance(headers, dict):
            headers = {k: v for k, v in headers.items() if v is not None}
        if isinstance(query, dict):
            query = {k: v for k, v in query.items() if v is not None}

        # Body can come from tool call args OR template; template wins if provided
        json_body = tool_def.http.json_body
        if json_body is None:
            json_body = args.get("json_body")
        json_body = self._render_template_obj(json_body, args, owner_email=owner_email, skill_id=skill_id)

        text_body = tool_def.http.text_body
        if text_body is None:
            text_body = args.get("text_body")
        text_body = self._render_template_obj(text_body, args, owner_email=owner_email, skill_id=skill_id)

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
