"""The Lead captured trigger: an automation that runs each time one of the account's agents captures a lead.

Leads delivers to other systems this way, rather than through webhooks of its own: the automation's steps (the REST
skill, email, an agent) do the delivering, and its runs are the record of what happened.

An active automation's enabled lead trigger is registered in the account's partition, so the dispatcher finds every
automation listening with one query instead of reading every automation's graph. A capture doesn't start them itself:
it saves a lead event (`leads/events.py`) with the lead, and `LeadEventDispatcher`, run by the scheduler, works
through the events. That keeps a capture fast, and no lead is lost to a restart between saving and starting.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from boto3.dynamodb.conditions import Key
from fastapi import HTTPException
from pydantic import BaseModel

from src.automations.errors import AutomationNotFoundError, AutomationValidationError
from src.automations.models import Automation, AutomationStatus, AutomationTrigger, AutomationTriggerType
from src.automations.triggers.models import LeadCapturedTriggerConfig
from src.agents.repository import AgentRepository
from src.config import settings
from src.db import get_dynamodb_resource
from src.leads.events import LeadEvent, LeadEventRepository
from src.leads.repository import LeadsRepository

if TYPE_CHECKING:
    from src.leads.models import Capture

log = logging.getLogger(__name__)


class LeadTriggerRegistration(BaseModel):
    """Key: `Account#{account_id}` / `LeadTrigger#{automation_id}#{trigger_id}`."""

    account_id: str
    automation_id: str
    trigger_id: str
    config: LeadCapturedTriggerConfig

    def matches(self, capture: Capture) -> bool:
        if capture.source == "dashboard" and not self.config.include_test_captures:
            return False
        if self.config.form_slug and self.config.form_slug != capture.form_slug:
            return False
        return not self.config.agent_id or self.config.agent_id == capture.agent_id

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            **self.model_dump(mode="json"),
            "pk": f"Account#{self.account_id}",
            "sk": f"LeadTrigger#{self.automation_id}#{self.trigger_id}",
            "entity_type": "LeadTriggerRegistration",
        }


class LeadTriggerRegistry:
    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def sync(self, automation: Automation, trigger: AutomationTrigger) -> None:
        """Listening while the automation is active and the trigger enabled; not otherwise."""
        listening = (
            trigger.type == AutomationTriggerType.LEAD_CAPTURED
            and trigger.enabled
            and automation.status == AutomationStatus.ACTIVE
        )
        if not listening:
            self.remove(automation.account_id, automation.automation_id, trigger.trigger_id)
            return
        config = LeadCapturedTriggerConfig.model_validate(trigger.config)
        _require_targets(automation.account_id, config)
        registration = LeadTriggerRegistration(
            account_id=automation.account_id,
            automation_id=automation.automation_id,
            trigger_id=trigger.trigger_id,
            config=config,
        )
        self.table.put_item(Item=registration.to_dynamo_item())

    def remove(self, account_id: str, automation_id: str, trigger_id: str) -> None:
        self.table.delete_item(Key={"pk": f"Account#{account_id}", "sk": f"LeadTrigger#{automation_id}#{trigger_id}"})

    def listening(self, account_id: str) -> list[LeadTriggerRegistration]:
        query: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(f"Account#{account_id}") & Key("sk").begins_with("LeadTrigger#")
        }
        registrations: list[LeadTriggerRegistration] = []
        while True:
            response = self.table.query(**query)
            registrations.extend(LeadTriggerRegistration.model_validate(item) for item in response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                return registrations
            query["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def _require_targets(account_id: str, config: LeadCapturedTriggerConfig) -> None:
    """A live trigger names a form and an agent of its own account, or none."""
    if config.form_slug and LeadsRepository().find_form_by_slug(account_id, config.form_slug) is None:
        raise AutomationValidationError(f"There is no lead form '{config.form_slug}' in this account")
    if config.agent_id and AgentRepository().find_in_account(account_id, config.agent_id) is None:
        raise AutomationValidationError("The lead trigger's agent isn't in this account")


#: Mistakes in one automation that trying again won't fix, so they're skipped rather than retried
NOT_RETRYABLE = (AutomationValidationError, AutomationNotFoundError, HTTPException)
BATCH = 25


def run_id_for(capture_id: str, trigger_id: str) -> str:
    """One run per lead and trigger, however often the lead's event is handled."""
    return hashlib.sha256(f"{capture_id}:{trigger_id}".encode()).hexdigest()[:32]


class LeadEventDispatcher:
    """Starts the automations listening for each captured lead. The scheduler runs it every few seconds.

    Every attempt is safe to repeat: an event is claimed before it is handled, a trigger whose run is started is
    remembered on the event, and a run has one fixed id. A failure leaves the event to come due again, a few times.
    """

    def __init__(self, events: LeadEventRepository | None = None, leads: LeadsRepository | None = None) -> None:
        self.events = events or LeadEventRepository()
        self.leads = leads or LeadsRepository()
        self.registry = LeadTriggerRegistry()

    def dispatch_due(self, now: datetime | None = None) -> int:
        """Handle the events that are due; how many this pass took."""
        now = now or datetime.now(timezone.utc)
        taken = 0
        for event in self.events.due(now, BATCH):
            claimed = self.events.claim(event, now)
            if claimed is None:  # another worker has it
                continue
            taken += 1
            self._handle(claimed, now)
        return taken

    def _handle(self, event: LeadEvent, now: datetime) -> None:
        capture = self.leads.find_capture(event.account_id, event.capture_id)
        if capture is None:  # deleted since, such as for a privacy request
            self.events.complete(event, now)
            return
        failed = False
        for registration in self.registry.listening(event.account_id):
            if registration.trigger_id in event.started or not registration.matches(capture):
                continue
            try:
                self._start(registration, capture)
            except NOT_RETRYABLE:
                log.warning(
                    "Skipping automation %s for lead %s", registration.automation_id, capture.capture_id, exc_info=True
                )
            except Exception:
                log.exception("Couldn't start automation %s for lead %s", registration.automation_id, capture.capture_id)
                failed = True
                continue
            self.events.record_started(event, registration.trigger_id)
        if failed:
            self.events.retry_later(event, now)
        else:
            self.events.complete(event, now)

    @staticmethod
    def _start(registration: LeadTriggerRegistration, capture: Capture) -> None:
        # Imported here: AutomationService keeps this module's registry in step with its triggers, so it imports us
        from src.automations.access import owner_of_automation
        from src.automations.dispatch import invoke_automation_run_async
        from src.automations.models import AutomationRunStatus
        from src.automations.repository import AutomationRepository
        from src.automations.runner import AutomationRunner
        from src.automations.service import AutomationService

        repository = AutomationRepository()
        automation = repository.find_in_account(capture.account_id, registration.automation_id)
        if automation is None or automation.status != AutomationStatus.ACTIVE:
            return
        owner = owner_of_automation(automation)
        run = repository.find_run_by_id(run_id_for(capture.capture_id, registration.trigger_id))
        if run is None:
            service = AutomationService(repo=repository)
            graph = service.get_graph(automation.automation_id, owner)
            service.validate_graph(graph.nodes, graph.edges, graph.triggers, owner)
            run = AutomationRunner(automation_repo=repository).create_lead_captured_run(
                graph, owner, registration.trigger_id, capture.event_payload(),
                run_id=run_id_for(capture.capture_id, registration.trigger_id),
            )
        elif run.status != AutomationRunStatus.PENDING:
            return  # an earlier attempt got it going
        # A run still pending here was created by an attempt that never got to start it
        invoke_automation_run_async(run.run_id, automation.automation_id, owner)
