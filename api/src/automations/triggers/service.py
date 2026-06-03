from __future__ import annotations

from src.automations.models import (
    Automation,
    AutomationStatus,
    AutomationTrigger,
    AutomationTriggerType,
)
from src.automations.triggers.models import ScheduleTriggerConfig
from src.scheduler.models import CreateScheduleRequest, ScheduleTargetType, UpdateScheduleRequest
from src.scheduler.service import SchedulerService, SchedulerValidationError


class AutomationTriggerLifecycleService:
    """Keeps trigger-owned external resources aligned with automation triggers."""

    def __init__(self, scheduler_service: SchedulerService | None = None):
        self.scheduler_service = scheduler_service or SchedulerService()

    def sync_trigger(self, automation: Automation, trigger: AutomationTrigger, owner_email: str) -> None:
        if trigger.type != AutomationTriggerType.SCHEDULE:
            return

        config = ScheduleTriggerConfig.model_validate(trigger.config)
        schedule_id = self.schedule_id_for(automation.automation_id, trigger.trigger_id)
        enabled = automation.status == AutomationStatus.ACTIVE and trigger.enabled
        target = {
            "automation_id": automation.automation_id,
            "trigger_id": trigger.trigger_id,
            "input": config.input,
        }
        source_ref = {
            "automation_id": automation.automation_id,
            "trigger_id": trigger.trigger_id,
        }

        if self.scheduler_service.repository.find_schedule(owner_email, schedule_id):
            self.scheduler_service.update_schedule(
                schedule_id,
                UpdateScheduleRequest(
                    name=trigger.name,
                    cron_expression=config.cron_expression,
                    timezone=config.timezone,
                    target=target,
                    source_ref=source_ref,
                    enabled=enabled,
                ),
                owner_email,
            )
            return

        self.scheduler_service.create_schedule(
            CreateScheduleRequest(
                schedule_id=schedule_id,
                name=trigger.name,
                cron_expression=config.cron_expression,
                timezone=config.timezone,
                target_type=ScheduleTargetType.AUTOMATION_RUN,
                target=target,
                source_type="automation_trigger",
                source_ref=source_ref,
                enabled=enabled,
            ),
            owner_email=owner_email,
            created_by=owner_email,
        )

    def delete_trigger(self, automation_id: str, trigger_id: str, owner_email: str) -> None:
        schedule_id = self.schedule_id_for(automation_id, trigger_id)
        try:
            self.scheduler_service.delete_schedule(schedule_id, owner_email)
        except SchedulerValidationError:
            return

    def pause_schedule_triggers(
        self,
        automation_id: str,
        triggers: list[AutomationTrigger],
        owner_email: str,
    ) -> None:
        for trigger in triggers:
            if trigger.type != AutomationTriggerType.SCHEDULE:
                continue
            schedule_id = self.schedule_id_for(automation_id, trigger.trigger_id)
            try:
                self.scheduler_service.pause_schedule(schedule_id, owner_email)
            except SchedulerValidationError:
                continue

    @staticmethod
    def schedule_id_for(automation_id: str, trigger_id: str) -> str:
        return f"automation:{automation_id}:trigger:{trigger_id}"
