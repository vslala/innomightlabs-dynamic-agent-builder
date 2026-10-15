"""The Lead captured trigger: an active automation runs for each new lead it listens for, and only those."""

import pytest

from src.automations.repository import AutomationRepository
from src.automations.triggers.lead_captured import LeadTriggerRegistry
from src.form_models import FormInput, FormInputType
from src.leads.models import CreateLeadFormRequest
from src.leads.service import CaptureOrigin, LeadsService
from src.skills.models import ActorKind
from tests.mock_data import AUTOMATION_CREATE_REQUEST, LeadsPlan, account_for
from tests.vision_support import create_memgpt_agent

FORM = CreateLeadFormRequest(slug="demo-request", name="Demo request",
                             form_inputs=[FormInput(input_type=FormInputType.TEXT, name="email", label="Email")])


@pytest.fixture
def started(monkeypatch) -> list[str]:
    """The runs dispatched, instead of running them."""
    run_ids: list[str] = []
    monkeypatch.setattr("src.automations.dispatch.invoke_automation_run_async",
                        lambda run_id, automation_id, owner: run_ids.append(run_id))
    return run_ids


@pytest.fixture
def account(dynamodb_table) -> str:
    account_id = account_for()
    LeadsService(limits=LeadsPlan()).create_form(account_id, "owner-1", FORM)
    return account_id


def automation_listening(test_client, auth_headers, *, active: bool = True, **config) -> str:
    graph = test_client.post("/automations", json=AUTOMATION_CREATE_REQUEST, headers=auth_headers).json()
    automation_id = graph["automation"]["automation_id"]
    trigger_id = graph["triggers"][0]["trigger_id"]
    updated = test_client.patch(
        f"/automations/{automation_id}/triggers/{trigger_id}",
        json={"type": "lead_captured", "enabled": True, "config": config},
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text
    if active:
        activated = test_client.patch(f"/automations/{automation_id}", json={"status": "active"}, headers=auth_headers)
        assert activated.status_code == 200, activated.text
    return automation_id


def capture(account: str, email: str = "jane@acme.com", *, agent_id: str = "agent-1", kind=ActorKind.VISITOR,
            leads: LeadsService | None = None):
    origin = CaptureOrigin(account_id=account, agent_id=agent_id, actor_kind=kind, actor_id="visitor-1")
    return (leads or LeadsService(limits=LeadsPlan())).capture("demo-request", {"email": email}, origin)


def test_a_new_lead_starts_the_automation_with_the_lead_in_its_trigger(test_client, auth_headers, account, started):
    automation_id = automation_listening(test_client, auth_headers, form_slug="demo-request")

    lead = capture(account).capture

    assert len(started) == 1
    run = AutomationRepository().find_run_by_id(started[0])
    assert run.automation_id == automation_id
    assert run.context["trigger"]["type"] == "lead_captured"
    assert run.context["trigger"]["lead"]["capture_id"] == lead.capture_id
    assert run.context["trigger"]["lead"]["answers"] == {"email": "jane@acme.com"}


def test_only_matching_leads_start_it(test_client, auth_headers, account, started):
    agent_id = create_memgpt_agent(test_client, auth_headers)
    automation_listening(test_client, auth_headers, form_slug="demo-request", agent_id=agent_id)

    capture(account, "other@acme.com", agent_id="another-agent")
    capture(account, "owner@acme.com", agent_id=agent_id, kind=ActorKind.OWNER)
    assert started == [], "another agent's lead, and a test lead from the dashboard"

    capture(account, agent_id=agent_id)
    assert len(started) == 1


def test_test_leads_start_it_when_asked_to(test_client, auth_headers, account, started):
    automation_listening(test_client, auth_headers, include_test_captures=True)

    capture(account, kind=ActorKind.OWNER)

    assert len(started) == 1


def test_a_repeated_or_locked_lead_starts_nothing(test_client, auth_headers, account, started):
    automation_listening(test_client, auth_headers)
    capture(account)
    capture(account)
    assert len(started) == 1, "the duplicate"

    limited = LeadsService(limits=LeadsPlan(lead_captures_per_month=1))
    locked = capture(account, "late@acme.com", leads=limited)

    assert locked.locked and len(started) == 1


def test_only_active_automations_listen(test_client, auth_headers, account, started):
    draft = automation_listening(test_client, auth_headers, active=False)
    live = automation_listening(test_client, auth_headers)
    assert [registration.automation_id for registration in LeadTriggerRegistry().listening(account)] == [live]

    disabled = test_client.patch(f"/automations/{live}", json={"status": "disabled"}, headers=auth_headers)
    assert disabled.status_code == 200, disabled.text
    capture(account)

    assert started == []
    assert LeadTriggerRegistry().listening(account) == []
    test_client.delete(f"/automations/{draft}", headers=auth_headers)


def test_deleting_the_automation_stops_it_listening(test_client, auth_headers, account):
    live = automation_listening(test_client, auth_headers)

    test_client.delete(f"/automations/{live}", headers=auth_headers)

    assert LeadTriggerRegistry().listening(account) == []


def test_a_trigger_for_a_form_the_account_doesnt_have_cant_go_live(test_client, auth_headers, account):
    automation_id = automation_listening(test_client, auth_headers, active=False, form_slug="no-such-form")

    refused = test_client.patch(f"/automations/{automation_id}", json={"status": "active"}, headers=auth_headers)

    assert refused.status_code == 422
    assert "no-such-form" in refused.json()["detail"]


def test_a_broken_automation_doesnt_lose_the_lead(test_client, auth_headers, account, monkeypatch):
    automation_listening(test_client, auth_headers)

    def explode(*args, **kwargs):
        raise RuntimeError("Lambda unavailable")

    monkeypatch.setattr("src.automations.dispatch.invoke_automation_run_async", explode)

    result = capture(account)

    assert not result.duplicate
    assert LeadsService(limits=LeadsPlan()).get_capture(account, result.capture.capture_id)


def test_the_trigger_form_offers_the_accounts_forms_and_agents(test_client, auth_headers, account):
    graph = test_client.post("/automations", json=AUTOMATION_CREATE_REQUEST, headers=auth_headers).json()

    form = test_client.get(f"/automations/{graph['automation']['automation_id']}/triggers/forms/lead_captured",
                           headers=auth_headers)

    assert form.status_code == 200, form.text
    inputs = {form_input["name"]: form_input for form_input in form.json()["form_inputs"]}
    assert [option["value"] for option in inputs["form_slug"]["options"]] == ["*", "demo-request"]
    assert inputs["agent_id"]["options"][0] == {"value": "*", "label": "Any agent", "group": None}


def test_steps_read_the_lead_through_smart_values(test_client, auth_headers, account, started):
    from src.automations.smart_values import SmartValueResolver

    automation_listening(test_client, auth_headers)
    capture(account)
    run = AutomationRepository().find_run_by_id(started[0])

    rendered = SmartValueResolver(run.context).render_template("New lead: {{ trigger.lead.answers.email }} via {{ trigger.lead.form_slug }}")

    assert rendered == "New lead: jane@acme.com via demo-request"
