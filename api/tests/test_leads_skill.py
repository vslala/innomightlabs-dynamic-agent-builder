"""The lead_capture skill as an agent uses it: check, show and capture against the account's own forms."""

import pytest

from src.form_models import FormInput, FormInputType, FormInputValidation, FormInputValidationFormat
from src.leads.models import CaptureFilters, CreateLeadFormRequest
from src.leads.service import LeadsService
from src.skills.registry import SkillRegistry
from tests.mock_data import TEST_USER_EMAIL, account_for

FORM = CreateLeadFormRequest(
    slug="demo-request",
    name="Demo request",
    form_inputs=[
        FormInput(input_type=FormInputType.TEXT, name="name", label="Full name"),
        FormInput(input_type=FormInputType.TEXT, name="email", label="Work email",
                  validation=FormInputValidation(format=FormInputValidationFormat.EMAIL)),
        FormInput(input_type=FormInputType.TEXT, name="company", label="Company", attr={"optional": "true"}),
    ],
)


@pytest.fixture
def account(dynamodb_table) -> str:
    account_id = account_for(TEST_USER_EMAIL)
    LeadsService().create_form(account_id, "owner-1", FORM)
    return account_id


def widget_run(account: str, **overrides) -> dict:
    """The runtime context SkillRuntimeService builds for a widget visitor's turn."""
    return {
        "agent_id": "agent-1",
        "account_id": account,
        "owner_id": "owner-1",
        "owner_email": TEST_USER_EMAIL,
        "actor_email": "jane@acme.com",
        "actor_id": "visitor-1",
        "actor_kind": "visitor",
        "conversation_id": "conv-1",
        **overrides,
    }


async def run(action: str, arguments: dict, context: dict):
    return await SkillRegistry().execute_action("lead_capture", action, arguments, config={}, context=context)


async def test_validate_lead_says_what_is_missing_without_saving(account):
    result = await run("validate_lead", {"form": "demo-request", "answers": {"name": "Jane", "email": "nope"}},
                       widget_run(account))

    assert result["complete"] is False
    assert set(result["invalid"]) == {"email"}
    assert LeadsService().list_captures(account, CaptureFilters(), limit=5).items == []


async def test_capture_lead_saves_into_the_runs_account_whatever_the_arguments_say(account):
    result = await run(
        "capture_lead",
        {"form": "demo-request", "answers": {"name": "Jane", "email": "jane@acme.com"}, "account_id": "someone-else"},
        widget_run(account),
    )

    assert result["ok"] is True and result["duplicate"] is False
    capture = LeadsService().get_capture(account, result["capture_id"])
    assert (capture.agent_id, capture.actor_id, capture.source) == ("agent-1", "visitor-1", "widget")


async def test_capture_lead_returns_what_to_fix_instead_of_failing(account):
    result = await run("capture_lead", {"form": "demo-request", "answers": {"name": "Jane"}}, widget_run(account))

    assert result == {"ok": False, "code": "INCOMPLETE", "message": "Still missing: email."}


async def test_a_retried_capture_is_reported_as_a_duplicate(account):
    arguments = {"form": "demo-request", "answers": {"name": "Jane", "email": "jane@acme.com"}}
    first = await run("capture_lead", arguments, widget_run(account))
    again = await run("capture_lead", arguments, widget_run(account, conversation_id="conv-2"))

    assert again == {"ok": True, "capture_id": first["capture_id"], "duplicate": True}


async def test_an_unknown_form_is_a_message_for_the_agent(account):
    result = await run("capture_lead", {"form": "nope", "answers": {}}, widget_run(account))

    assert result["ok"] is False and result["code"] == "FORM_NOT_FOUND"


async def test_render_lead_form_shows_the_stored_form_with_what_is_known(account):
    payload = await run("render_lead_form", {"form": "demo-request", "prefill": {"name": "Jane"}}, widget_run(account))

    assert payload["type"] == "ui_form_render" and payload["lead_form"] == "demo-request"
    assert payload["form"]["form_name"] == "Demo request"
    assert [form_input["name"] for form_input in payload["form"]["form_inputs"]] == ["email", "company"]

    everything = await run(
        "render_lead_form", {"form": "demo-request", "prefill": {"name": "Jane"}, "only_missing": False},
        widget_run(account),
    )
    assert everything["form"]["form_inputs"][0]["value"] == "Jane"


async def test_register_lead_still_works_and_now_lands_in_leads(account, monkeypatch):
    sent = []
    monkeypatch.setattr("src.skills.lead_capture.actions.send_email", lambda *args: sent.append(args) or True)
    arguments = {
        "form_label": "Request a demo",
        "answers": [
            {"field_id": "email", "label": "Work email", "value": "jane@acme.com"},
            {"field_id": "contact_consent", "label": "I agree", "value": "yes"},
        ],
    }

    first = await run("register_lead", arguments, widget_run(account))
    await run("register_lead", arguments, widget_run(account))

    assert first["ok"] is True and first["email_sent"] is True
    assert len(sent) == 1, "a repeated registration doesn't email twice"
    capture = LeadsService().get_capture(account, first["lead_id"])
    assert capture.form_name == "Request a demo" and capture.form_id is None
    assert capture.answers == {"email": "jane@acme.com", "contact_consent": "yes"}
