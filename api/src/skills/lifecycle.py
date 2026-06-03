from __future__ import annotations

import asyncio
import inspect
import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from src.skills.models import LoadedSkill, SkillActionManifest, SkillLifecycleHook
from src.skills.registry import SkillRegistry, get_skill_registry

log = logging.getLogger(__name__)


class SkillLifecycleEvent(str, Enum):
    DELETE = "delete"


class SkillLifecycleTargetType(str, Enum):
    AGENT_SKILL = "agent_skill"
    AUTOMATION_ACTION = "automation_action"


class SkillLifecycleContext(BaseModel):
    event: SkillLifecycleEvent
    target_type: SkillLifecycleTargetType
    owner_email: str
    skill_id: str
    installed_skill_id: str | None = None
    action: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    arguments: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillLifecycleRunner:
    """Runs optional skill lifecycle hooks without blocking destructive operations."""

    def __init__(self, registry: SkillRegistry | None = None):
        self.registry = registry or get_skill_registry()

    def run_skill_delete(
        self,
        *,
        skill_id: str,
        installed_skill_id: str | None,
        owner_email: str,
        config: dict[str, Any],
        metadata: dict[str, Any],
    ) -> None:
        loaded = self.registry.get(skill_id)
        if not loaded:
            return
        context = SkillLifecycleContext(
            event=SkillLifecycleEvent.DELETE,
            target_type=SkillLifecycleTargetType.AGENT_SKILL,
            owner_email=owner_email,
            skill_id=skill_id,
            installed_skill_id=installed_skill_id,
            config=config,
            metadata=metadata,
        )
        self._run_background(loaded, loaded.manifest.lifecycle.delete, context)

    def run_action_delete(
        self,
        *,
        skill_id: str,
        installed_skill_id: str | None,
        action_name: str,
        owner_email: str,
        config: dict[str, Any],
        arguments: dict[str, Any],
        metadata: dict[str, Any],
    ) -> None:
        loaded = self.registry.get(skill_id)
        if not loaded:
            return
        action = self._find_action(loaded, action_name)
        if not action:
            return
        context = SkillLifecycleContext(
            event=SkillLifecycleEvent.DELETE,
            target_type=SkillLifecycleTargetType.AUTOMATION_ACTION,
            owner_email=owner_email,
            skill_id=skill_id,
            installed_skill_id=installed_skill_id,
            action=action.name,
            config=config,
            arguments=arguments,
            metadata=metadata,
        )
        self._run_background(loaded, action.lifecycle.delete, context)

    def _run_background(
        self,
        loaded: LoadedSkill,
        hook: SkillLifecycleHook | None,
        context: SkillLifecycleContext,
    ) -> None:
        if not hook:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self._execute(loaded, hook, context))
            return
        loop.create_task(self._execute(loaded, hook, context))

    async def _execute(
        self,
        loaded: LoadedSkill,
        hook: SkillLifecycleHook,
        context: SkillLifecycleContext,
    ) -> None:
        try:
            func = self.registry._resolve_handler(loaded.folder_name, hook.handler)
            result = func(context=context)
            if inspect.isawaitable(result):
                await result
        except Exception:
            log.exception(
                "Skill lifecycle hook failed: skill=%s action=%s event=%s target=%s",
                context.skill_id,
                context.action,
                context.event.value,
                context.target_type.value,
            )

    def _find_action(
        self,
        loaded: LoadedSkill,
        action_name: str,
    ) -> SkillActionManifest | None:
        return next(
            (
                action
                for action in loaded.manifest.actions
                if action.name == action_name or action_name in action.aliases
            ),
            None,
        )
