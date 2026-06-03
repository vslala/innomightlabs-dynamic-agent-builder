from __future__ import annotations

from typing import Any

from src.scheduler.repository import SchedulerRepository
from src.scheduler.service import SchedulerService
from src.skills.lifecycle import SkillLifecycleContext

async def on_delete(context: SkillLifecycleContext) -> dict[str, Any]:
    automation_id = str(context.metadata.get("automation_id") or "").strip()
    automation_node_id = str(context.metadata.get("automation_node_id") or "").strip()
    if not automation_id:
        return {"deleted": 0, "reason": "missing_automation_id"}

    repository = SchedulerRepository()
    service = SchedulerService(repository=repository)
    deleted: list[str] = []
    for schedule in repository.list_schedules_for_automation(automation_id):
        if schedule.source_type != "automation_skill":
            continue
        if schedule.source_ref.get("automation_id") != automation_id:
            continue
        if automation_node_id and schedule.source_ref.get("automation_node_id") != automation_node_id:
            continue
        service.delete_schedule(schedule.schedule_id, context.owner_email)
        deleted.append(schedule.schedule_id)

    return {"deleted": len(deleted), "schedule_ids": deleted}
