from __future__ import annotations

import importlib
import logging
from typing import Optional

from fastapi import APIRouter

from src.skills.models import LoadedSkill

log = logging.getLogger(__name__)


def _resolve_router_attr(folder_name: str, handler: str) -> Optional[APIRouter]:
    """Resolve an APIRouter from a handler string.

    Handler formats:
    - "router:router"  -> module="router" attr="router"
    - "router.router"  -> module="router" attr="router"
    - "src.skills.some_skill.router:router" -> fully qualified module

    If module is not fully qualified, it's assumed relative to src.skills.<folder_name>.
    """

    module_part: str
    attr_name: str

    if ":" in handler:
        module_part, attr_name = handler.split(":", 1)
    else:
        module_part, attr_name = handler.rsplit(".", 1)

    module_path = module_part
    if not module_path.startswith("src."):
        module_path = f"src.skills.{folder_name}.{module_path}"

    module = importlib.import_module(module_path)
    router = getattr(module, attr_name, None)
    if router is None:
        raise ValueError(f"Router attribute '{attr_name}' not found in module '{module_path}'")
    if not isinstance(router, APIRouter):
        raise ValueError(f"Resolved object '{module_path}.{attr_name}' is not an APIRouter")
    return router


def build_skill_api_routers(skills: list[LoadedSkill]) -> list[tuple[str, APIRouter]]:
    """Build a list of (prefix, router) for skill-owned routers.

    Routers are mounted under: /skills/{skill_id}

    If a skill declares api_router but cannot be imported, we skip it and log.
    This makes skills removable without breaking app startup.
    """

    mounted: list[tuple[str, APIRouter]] = []

    for loaded in skills:
        spec = loaded.manifest.api_router
        if not spec:
            continue

        try:
            router = _resolve_router_attr(loaded.folder_name, spec)
            prefix = f"/skills/{loaded.manifest.id}"
            mounted.append((prefix, router))
        except Exception as e:
            log.warning(
                "Failed to load api_router for skill %s (%s): %s",
                loaded.manifest.id,
                loaded.folder_name,
                e,
            )

    return mounted
