from __future__ import annotations

from typing import Any

from src.knowledge.recrawl import recrawl as recrawl_knowledge_base
from src.skills.runtime_context import run_owner


async def recrawl(
    arguments: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    del config
    kb_id = str(arguments.get("knowledge_base_id") or "").strip()
    if not kb_id:
        raise ValueError("Missing knowledge base")
    result = recrawl_knowledge_base(kb_id, run_owner(context))
    return {"started": result.started, "message": result.message, "job_id": result.job_id}
