from __future__ import annotations

import json
from typing import Any

from src.scheduler.models import CreateScheduleRequest, ScheduleTargetType, UpdateScheduleRequest
from src.scheduler.service import SchedulerService


def _required_context(context: dict[str, Any], key: str) -> str:
    value = str(context.get(key) or "").strip()
    if not value:
        raise ValueError(f"Missing scheduler runtime context: {key}")
    return value


def _required_argument(arguments: dict[str, Any], key: str) -> str:
    value = str(arguments.get(key) or "").strip()
    if not value:
        raise ValueError(f"Missing scheduler argument: {key}")
    return value


def _required_argument_or_context(
    arguments: dict[str, Any],
    context: dict[str, Any],
    key: str,
) -> str:
    value = str(arguments.get(key) or context.get(key) or "").strip()
    if not value:
        raise ValueError(f"Missing scheduler argument or runtime context: {key}")
    return value


def _schedule_response(schedule) -> dict[str, Any]:
    return schedule.to_response().model_dump(mode="json")


def _agent_message_target(arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    message = str(arguments.get("message") or "").strip()
    if not message:
        raise ValueError("Missing scheduled message")

    owner_email = _required_context(context, "owner_email")
    actor_email = str(context.get("actor_email") or owner_email).strip()
    actor_id = str(context.get("actor_id") or actor_email).strip()
    return {
        "agent_id": _required_argument_or_context(arguments, context, "agent_id"),
        "conversation_id": _required_context(context, "conversation_id"),
        "message": message,
        "conversation_policy": "existing",
        "actor_email": actor_email,
        "actor_id": actor_id,
    }


def _automation_input(arguments: dict[str, Any]) -> dict[str, Any]:
    raw_input = arguments.get("input")
    if isinstance(raw_input, dict):
        return raw_input
    input_json = str(arguments.get("input_json") or "").strip()
    if not input_json:
        return {}
    parsed = json.loads(input_json)
    if not isinstance(parsed, dict):
        raise ValueError("Automation schedule input_json must parse to an object")
    return parsed


async def create_or_update(
    arguments: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    del config

    owner_email = _required_context(context, "owner_email")
    target = _agent_message_target(arguments, context)
    source_ref = {
        "agent_id": target["agent_id"],
        "conversation_id": target["conversation_id"],
    }
    service = SchedulerService()
    schedule_id = str(arguments.get("schedule_id") or "").strip()

    if schedule_id:
        schedule = service.update_schedule(
            schedule_id,
            UpdateScheduleRequest(
                name=str(arguments.get("name") or "").strip() or None,
                cron_expression=str(arguments.get("cron_expression") or "").strip() or None,
                timezone=str(arguments.get("timezone") or "").strip() or None,
                target=target,
                source_ref=source_ref,
                enabled=True,
            ),
            owner_email,
        )
    else:
        schedule = service.create_schedule(
            CreateScheduleRequest(
                name=str(arguments.get("name") or "").strip(),
                cron_expression=str(arguments.get("cron_expression") or "").strip(),
                timezone=str(arguments.get("timezone") or "UTC").strip() or "UTC",
                target_type=ScheduleTargetType.AGENT_MESSAGE,
                target=target,
                source_type="agent_skill",
                source_ref=source_ref,
                enabled=True,
            ),
            owner_email=owner_email,
            created_by=str(context.get("actor_email") or owner_email),
        )

    return {
        "schedule": _schedule_response(schedule),
        "message": "Schedule saved for this conversation.",
    }


async def schedule_automation(
    arguments: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    del config

    owner_email = _required_context(context, "owner_email")
    automation_id = _required_context(context, "automation_id")
    target = {
        "automation_id": automation_id,
        "input": _automation_input(arguments),
    }
    trigger_id = str(context.get("automation_node_id") or "").strip()
    if trigger_id:
        target["trigger_id"] = trigger_id
    source_ref = {
        "automation_id": automation_id,
        "automation_node_id": str(context.get("automation_node_id") or "").strip(),
    }
    service = SchedulerService()
    schedule_id = _required_argument(arguments, "schedule_id")

    if service.repository.find_schedule(owner_email, schedule_id):
        schedule = service.update_schedule(
            schedule_id,
            UpdateScheduleRequest(
                name=str(arguments.get("name") or "").strip() or None,
                cron_expression=str(arguments.get("cron_expression") or "").strip() or None,
                timezone=str(arguments.get("timezone") or "").strip() or None,
                target=target,
                source_ref=source_ref,
                enabled=True,
            ),
            owner_email,
        )
    else:
        schedule = service.create_schedule(
            CreateScheduleRequest(
                schedule_id=schedule_id,
                name=str(arguments.get("name") or "").strip(),
                cron_expression=str(arguments.get("cron_expression") or "").strip(),
                timezone=str(arguments.get("timezone") or "UTC").strip() or "UTC",
                target_type=ScheduleTargetType.AUTOMATION_RUN,
                target=target,
                source_type="automation_skill",
                source_ref=source_ref,
                enabled=True,
            ),
            owner_email=owner_email,
            created_by=str(context.get("actor_email") or owner_email),
        )

    return {
        "schedule": _schedule_response(schedule),
        "message": "Automation schedule saved.",
    }


async def pause(
    arguments: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    del config
    schedule = SchedulerService().pause_schedule(
        str(arguments.get("schedule_id") or "").strip(),
        _required_context(context, "owner_email"),
    )
    return {"schedule": _schedule_response(schedule), "message": "Schedule paused."}


async def resume(
    arguments: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    del config
    schedule = SchedulerService().resume_schedule(
        str(arguments.get("schedule_id") or "").strip(),
        _required_context(context, "owner_email"),
    )
    return {"schedule": _schedule_response(schedule), "message": "Schedule resumed."}


async def delete(
    arguments: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    del config
    schedule_id = str(arguments.get("schedule_id") or "").strip()
    SchedulerService().delete_schedule(schedule_id, _required_context(context, "owner_email"))
    return {"schedule_id": schedule_id, "deleted": True}


async def list_schedules(
    arguments: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    del arguments, config
    owner_email = _required_context(context, "owner_email")
    agent_id = _required_context(context, "agent_id")
    conversation_id = _required_context(context, "conversation_id")
    schedules = [
        schedule
        for schedule in SchedulerService().list_schedules(owner_email)
        if schedule.target.get("agent_id") == agent_id
        and schedule.target.get("conversation_id") == conversation_id
    ]
    return {"schedules": [_schedule_response(schedule) for schedule in schedules]}
