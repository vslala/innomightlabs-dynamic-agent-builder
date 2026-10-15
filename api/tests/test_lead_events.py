"""Starting automations for captured leads survives restarts and failures: every capture leaves an event, and the
scheduler's dispatcher works through the events until each is done."""

from datetime import datetime, timedelta, timezone

import pytest

from src.automations.models import AutomationRunStatus
from src.automations.repository import AutomationRepository
from src.automations.triggers.lead_captured import LeadEventDispatcher, run_id_for
from src.form_models import FormInput, FormInputType
from src.leads.events import FIRST_RETRY_DELAY, LEASE, MAX_ATTEMPTS, LeadEventRepository
from src.leads.models import CreateLeadFormRequest
from src.leads.service import CaptureOrigin, LeadsService
from src.scheduler.runtime import LEAD_EVENT_DISPATCHER_ID, SchedulerRuntime
from src.skills.models import ActorKind
from tests.mock_data import AUTOMATION_CREATE_REQUEST, LeadsPlan, account_for

FORM = CreateLeadFormRequest(slug="demo-request", name="Demo request",
                             form_inputs=[FormInput(input_type=FormInputType.TEXT, name="email", label="Email")])
LATER = timedelta(hours=1)


class Dispatches:
    """The runs handed to the runner, and whether handing one over fails."""

    def __init__(self) -> None:
        self.run_ids: list[str] = []
        self.failing = False

    def __call__(self, run_id: str, automation_id: str, owner) -> None:
        if self.failing:
            raise RuntimeError("worker unavailable")
        self.run_ids.append(run_id)


@pytest.fixture
def dispatches(monkeypatch) -> Dispatches:
    fake = Dispatches()
    monkeypatch.setattr("src.automations.dispatch.invoke_automation_run_async", fake)
    return fake


@pytest.fixture
def account(dynamodb_table) -> str:
    account_id = account_for()
    LeadsService(limits=LeadsPlan()).create_form(account_id, "owner-1", FORM)
    return account_id


@pytest.fixture
def listening(test_client, auth_headers, account) -> str:
    graph = test_client.post("/automations", json=AUTOMATION_CREATE_REQUEST, headers=auth_headers).json()
    automation_id, trigger_id = graph["automation"]["automation_id"], graph["triggers"][0]["trigger_id"]
    test_client.patch(f"/automations/{automation_id}/triggers/{trigger_id}",
                      json={"type": "lead_captured", "enabled": True, "config": {}}, headers=auth_headers)
    activated = test_client.patch(f"/automations/{automation_id}", json={"status": "active"}, headers=auth_headers)
    assert activated.status_code == 200, activated.text
    return automation_id


def capture(account: str, email: str = "jane@acme.com", plan: LeadsPlan | None = None):
    origin = CaptureOrigin(account_id=account, agent_id="agent-1", actor_kind=ActorKind.VISITOR, actor_id="visitor-1")
    return LeadsService(limits=plan or LeadsPlan()).capture("demo-request", {"email": email}, origin)


def waiting(now: datetime | None = None) -> int:
    """Events due at `now` (or an hour on, when they're all due)."""
    return len(LeadEventRepository().due(now or datetime.now(timezone.utc) + LATER, 50))


def now() -> datetime:
    return datetime.now(timezone.utc)


def test_a_capture_leaves_an_event_and_starts_nothing_itself(account, listening, dispatches):
    capture(account)

    assert waiting() == 1
    assert dispatches.run_ids == []


def test_duplicate_and_locked_captures_leave_no_event(account, listening, dispatches):
    capture(account)
    capture(account)
    capture(account, "late@acme.com", plan=LeadsPlan(lead_captures_per_month=1))

    assert waiting() == 1, "the duplicate has none, nor does the lead past the plan's limit"


def test_dispatching_starts_the_run_once(account, listening, dispatches):
    lead = capture(account).capture

    assert LeadEventDispatcher().dispatch_due() == 1
    assert LeadEventDispatcher().dispatch_due() == 0, "the event is done"

    assert dispatches.run_ids == [run_id_for(lead.capture_id, _trigger_id(listening))]
    assert waiting() == 0


def _trigger_id(automation_id: str) -> str:
    return AutomationRepository().get_graph(automation_id)[2][0].trigger_id


def test_a_failure_to_start_is_retried_later_and_makes_one_run(account, listening, dispatches):
    lead = capture(account).capture
    dispatches.failing = True

    LeadEventDispatcher().dispatch_due()

    run_id = run_id_for(lead.capture_id, _trigger_id(listening))
    assert AutomationRepository().find_run_by_id(run_id).status == AutomationRunStatus.PENDING, "created, not started"
    assert waiting(now()) == 0, "not due again until its wait is over"

    dispatches.failing = False
    assert LeadEventDispatcher().dispatch_due(now() + FIRST_RETRY_DELAY + timedelta(seconds=1)) == 1

    assert dispatches.run_ids == [run_id]
    assert len(AutomationRepository().find_runs_by_automation(listening, 10, None)[0]) == 1


def test_an_event_is_given_up_on_after_its_last_attempt(account, listening, dispatches):
    capture(account)
    dispatches.failing = True
    moment = now()

    for attempt in range(MAX_ATTEMPTS):
        assert LeadEventDispatcher().dispatch_due(moment) == 1, attempt
        moment += LATER

    assert LeadEventDispatcher().dispatch_due(moment) == 0, "it isn't tried again"
    assert waiting() == 0


def test_a_worker_that_dies_leaves_the_event_to_come_due_again(account, listening, dispatches):
    capture(account)
    events = LeadEventRepository()
    [event] = events.due(now() + LATER, 5)
    assert events.claim(event, now()) is not None  # a worker takes it, then dies

    assert LeadEventDispatcher().dispatch_due() == 0, "still its lease"
    assert LeadEventDispatcher().dispatch_due(now() + LEASE + timedelta(seconds=1)) == 1
    assert len(dispatches.run_ids) == 1


def test_two_workers_cannot_take_the_same_event(account, listening, dispatches):
    capture(account)
    events = LeadEventRepository()
    [event] = events.due(now() + LATER, 5)

    first, second = events.claim(event, now()), events.claim(event, now())

    assert first is not None and second is None


def test_one_broken_automation_does_not_hold_up_the_others(test_client, auth_headers, account, listening, dispatches):
    second = test_client.post("/automations", json={**AUTOMATION_CREATE_REQUEST, "title": "Second"},
                              headers=auth_headers).json()
    second_id, second_trigger = second["automation"]["automation_id"], second["triggers"][0]["trigger_id"]
    test_client.patch(f"/automations/{second_id}/triggers/{second_trigger}",
                      json={"type": "lead_captured", "enabled": True, "config": {}}, headers=auth_headers)
    test_client.patch(f"/automations/{second_id}", json={"status": "active"}, headers=auth_headers)
    # The first can no longer be run: its owner's identity is gone
    first = AutomationRepository().find_in_account(account, listening)
    first.owner_id = "someone-who-left"
    AutomationRepository().save_automation(first)

    capture(account)
    LeadEventDispatcher().dispatch_due()

    assert len(dispatches.run_ids) == 1, "the second still started"
    assert waiting() == 0, "the broken one is skipped, not retried"


def test_a_lead_deleted_before_its_event_is_handled_is_dropped(account, listening, dispatches):
    lead = capture(account).capture
    LeadsService().delete_capture(account, lead.capture_id)

    assert LeadEventDispatcher().dispatch_due() == 1
    assert dispatches.run_ids == []
    assert waiting() == 0


async def test_the_scheduler_runs_the_dispatcher(dynamodb_table):
    runtime = SchedulerRuntime()
    await runtime.start()
    try:
        assert runtime.scheduler.get_job(LEAD_EVENT_DISPATCHER_ID) is not None
    finally:
        await runtime.stop()
