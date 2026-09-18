"""Validated, idempotent Dream memory action execution."""

from __future__ import annotations

from dataclasses import dataclass

from src.dream.models import DreamAction, DreamActionOutcome, DreamActionType
from src.dream.redaction import is_safe
from src.memory.models import CoreMemory
from src.memory.repository import MemoryRepository
from src.tools.native.handlers import normalize_block_name


@dataclass
class DreamActionContext:
    agent_id: str
    user_id: str
    memory_repository: MemoryRepository


class DreamActionExecutor:
    """Applies one plan against a fresh memory read, preserving line semantics."""

    def execute(
        self,
        context: DreamActionContext,
        actions: list[DreamAction],
        min_confidence: float,
    ) -> list[tuple[DreamAction, DreamActionOutcome, str]]:
        ordered = sorted(
            actions,
            key=lambda action: action.line_number or 0,
            reverse=True,
        )
        results: list[tuple[DreamAction, DreamActionOutcome, str]] = []
        for action in ordered:
            results.append((action, *self._execute_one(context, action, min_confidence)))
        return results

    def _execute_one(
        self, context: DreamActionContext, action: DreamAction, min_confidence: float
    ) -> tuple[DreamActionOutcome, str]:
        if action.confidence < min_confidence:
            return DreamActionOutcome.SKIPPED_LOW_CONFIDENCE, "below configured confidence threshold"
        if not is_safe(action.content):
            return DreamActionOutcome.SKIPPED_REDACTED, "content matched a secret pattern"
        if action.type == DreamActionType.NO_OP:
            return DreamActionOutcome.EXECUTED, "no memory mutation requested"
        if action.type == DreamActionType.INSERT_ARCHIVAL:
            if not action.content.strip():
                return DreamActionOutcome.FAILED, "archival content is required"
            _, is_new = context.memory_repository.insert_archival(
                context.agent_id, context.user_id, action.content.strip()
            )
            return (
                (DreamActionOutcome.EXECUTED, "archival memory inserted")
                if is_new
                else (DreamActionOutcome.SKIPPED_DUPLICATE, "archival content already exists")
            )

        block_name = normalize_block_name(action.block_name)
        if not block_name or not context.memory_repository.get_block_definition(
            context.agent_id, context.user_id, block_name
        ):
            return DreamActionOutcome.SKIPPED_UNKNOWN_BLOCK, "memory block does not exist"
        memory = context.memory_repository.get_core_memory(context.agent_id, context.user_id, block_name)
        if memory is None:
            memory = CoreMemory(agent_id=context.agent_id, user_id=context.user_id, block_name=block_name)

        if action.type == DreamActionType.APPEND_CORE:
            if not action.content.strip():
                return DreamActionOutcome.FAILED, "core content is required"
            if context.memory_repository.line_exists(
                context.agent_id, context.user_id, block_name, action.content.strip()
            ) is not None:
                return DreamActionOutcome.SKIPPED_DUPLICATE, "core line already exists"
            memory.lines.append(action.content.strip())
        elif action.type in {DreamActionType.REPLACE_CORE, DreamActionType.DELETE_CORE}:
            if action.line_number is None or not 1 <= action.line_number <= len(memory.lines):
                return DreamActionOutcome.SKIPPED_STALE_LINE, "line number no longer exists"
            if action.type == DreamActionType.REPLACE_CORE:
                if not action.content.strip():
                    return DreamActionOutcome.FAILED, "replacement content is required"
                memory.lines[action.line_number - 1] = action.content.strip()
            else:
                memory.lines.pop(action.line_number - 1)
        else:
            return DreamActionOutcome.FAILED, "unsupported action"

        context.memory_repository.save_core_memory(memory)
        return DreamActionOutcome.EXECUTED, "memory updated"
