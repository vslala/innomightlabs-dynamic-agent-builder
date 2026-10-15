"""Lead forms and captures: what an agent may save, how often, and what the account then sees."""

import pytest

from src.form_models import FormInput, FormInputType, FormInputValidation, FormInputValidationFormat
from src.leads.errors import LeadsError
from src.leads.repository import DuplicateCapture
from src.leads.models import CaptureFilters, CreateLeadFormRequest, LeadFormFields, LeadSettingsRequest, LeadStatus
from src.leads.service import CaptureOrigin, LeadsService
from src.skills.models import ActorKind
from tests.mock_data import LeadsPlan as Plan

ACCOUNT = "acct-1"


DEMO_INPUTS = [
    FormInput(input_type=FormInputType.TEXT, name="name", label="Full name"),
    FormInput(
        input_type=FormInputType.TEXT, name="email", label="Work email",
        validation=FormInputValidation(format=FormInputValidationFormat.EMAIL),
        attr={"agent_hint": "Ask only after you have helped them."},
    ),
    FormInput(input_type=FormInputType.TEXT, name="company", label="Company", attr={"optional": "true"}),
    FormInput(input_type=FormInputType.CHOICE, name="consent", label="I agree to be contacted", values=["yes"],
              attr={"variant": "checkbox"}),
]
JANE = {"name": "Jane Doe", "email": "Jane@Acme.com", "consent": "yes"}


@pytest.fixture
def leads(dynamodb_table) -> LeadsService:
    return LeadsService(limits=Plan())


def demo_form(leads: LeadsService, slug: str = "demo-request"):
    return leads.create_form(ACCOUNT, "owner-1", CreateLeadFormRequest(slug=slug, name="Demo request",
                                                                        form_inputs=DEMO_INPUTS))


def visitor(actor_id: str = "visitor-1", conversation_id: str = "conv-1") -> CaptureOrigin:
    return CaptureOrigin(account_id=ACCOUNT, agent_id="agent-1", conversation_id=conversation_id,
                         actor_kind=ActorKind.VISITOR, actor_id=actor_id)


def owner_testing() -> CaptureOrigin:
    return CaptureOrigin(account_id=ACCOUNT, agent_id="agent-1", actor_kind=ActorKind.OWNER, actor_id="owner-1")


# Forms

def test_a_form_fills_in_the_lead_defaults(leads):
    form = demo_form(leads)

    assert form.version == 1
    assert form.form_inputs[0].validation.max_length == 2000
    assert form.form_inputs[3].validation.max_length is None, "choices are bounded by their options"


@pytest.mark.parametrize("bad_input", [
    FormInput(input_type=FormInputType.PASSWORD, name="pin", label="PIN"),
    FormInput(input_type=FormInputType.TEXT, name="Bad Name", label="Bad"),
    FormInput(input_type=FormInputType.SELECT, name="size", label="Size"),
    FormInput(input_type=FormInputType.TEXT, name="code", label="Code", validation=FormInputValidation(pattern="(")),
    FormInput(input_type=FormInputType.TEXT, name="notes", label="Notes", attr={"smart_values": "true"}),
    FormInput(input_type=FormInputType.FILE_UPLOAD, name="sheet", label="Sheet",
              validation=FormInputValidation(accept=["text/csv"])),
    FormInput(input_type=FormInputType.FILE_UPLOAD, name="many", label="Many", validation=FormInputValidation(max_items=9)),
])
def test_forms_only_use_inputs_visitors_may_see(leads, bad_input):
    with pytest.raises(ValueError):
        CreateLeadFormRequest(slug="bad-form", name="Bad", form_inputs=[bad_input])


def test_slugs_are_unique_in_the_account(leads):
    demo_form(leads)
    with pytest.raises(LeadsError) as refused:
        demo_form(leads)
    assert refused.value.code == "SLUG_TAKEN"


def test_changing_inputs_is_a_new_version_but_renaming_is_not(leads):
    form = demo_form(leads)

    renamed = leads.update_form(ACCOUNT, form.form_id, LeadFormFields(name="Book a demo", form_inputs=DEMO_INPUTS))
    assert (renamed.name, renamed.version) == ("Book a demo", 1)

    revised = leads.update_form(ACCOUNT, form.form_id, LeadFormFields(name="Book a demo", form_inputs=DEMO_INPUTS[:2]))
    assert revised.version == 2
    assert leads.get_form(ACCOUNT, form.form_id).version == 2


def test_a_form_with_leads_is_archived_not_deleted(leads):
    form = demo_form(leads)
    leads.capture("demo-request", JANE, visitor())

    with pytest.raises(LeadsError) as refused:
        leads.delete_form(ACCOUNT, form.form_id)
    assert refused.value.code == "FORM_HAS_CAPTURES"

    leads.archive_form(ACCOUNT, form.form_id)
    with pytest.raises(LeadsError) as closed:
        leads.capture("demo-request", {**JANE, "name": "Other"}, visitor("visitor-2"))
    assert closed.value.code == "FORM_ARCHIVED"


def test_an_unused_form_can_be_deleted(leads):
    form = demo_form(leads)
    leads.delete_form(ACCOUNT, form.form_id)

    assert leads.list_forms(ACCOUNT) == []
    demo_form(leads)  # the slug is free again


def test_the_plan_limits_active_forms(dynamodb_table):
    leads = LeadsService(limits=Plan(lead_forms=1))
    form = demo_form(leads)
    with pytest.raises(LeadsError) as refused:
        demo_form(leads, slug="second-form")
    assert refused.value.code == "PLAN_LIMIT"

    leads.archive_form(ACCOUNT, form.form_id)
    second = demo_form(leads, slug="second-form")
    with pytest.raises(LeadsError):
        leads.restore_form(ACCOUNT, form.form_id)
    assert second.is_active


# Captures

def test_a_capture_stores_normalised_answers_and_the_form_it_was_given_for(leads):
    form = demo_form(leads)

    result = leads.capture("demo-request", JANE, visitor())

    capture = result.capture
    assert not result.duplicate and not result.locked
    assert capture.answers == {"name": "Jane Doe", "email": "jane@acme.com", "consent": "yes"}
    assert (capture.form_id, capture.form_version, capture.status, capture.source) == (form.form_id, 1, "new", "widget")
    assert [form_input.name for form_input in capture.form_inputs] == ["name", "email", "company", "consent"]
    assert leads.get_form(ACCOUNT, form.form_id).capture_count == 1


def test_an_incomplete_capture_says_what_to_fix_and_saves_nothing(leads):
    demo_form(leads)

    with pytest.raises(LeadsError) as refused:
        leads.capture("demo-request", {"name": "Jane", "email": "not-an-email", "budget": "1k"}, visitor())

    assert refused.value.code == "INCOMPLETE"
    assert "Still missing: consent." in refused.value.message
    assert "email" in refused.value.message and "budget" in refused.value.message
    assert leads.list_captures(ACCOUNT, CaptureFilters(), limit=10).items == []


def test_the_same_lead_twice_is_one_capture_even_across_conversations(leads):
    form = demo_form(leads)

    first = leads.capture("demo-request", JANE, visitor(conversation_id="conv-1"))
    again = leads.capture("demo-request", JANE, visitor(conversation_id="conv-2"))
    changed = leads.capture("demo-request", {**JANE, "company": "Acme"}, visitor())

    assert again.duplicate and again.capture.capture_id == first.capture.capture_id
    assert not changed.duplicate
    assert len(leads.list_captures(ACCOUNT, CaptureFilters(), limit=10).items) == 2
    assert leads.get_form(ACCOUNT, form.form_id).capture_count == 2
    assert leads.usage(ACCOUNT).captures == 2, "a duplicate is not counted"


def test_dashboard_captures_are_tests_hidden_by_default_and_not_counted(leads):
    demo_form(leads)
    leads.capture("demo-request", JANE, owner_testing())

    assert leads.list_captures(ACCOUNT, CaptureFilters(), limit=10).items == []
    shown = leads.list_captures(ACCOUNT, CaptureFilters(include_tests=True), limit=10).items
    assert [capture.source for capture in shown] == ["dashboard"]
    assert leads.usage(ACCOUNT).captures == 0


def test_captures_past_the_monthly_limit_are_kept_but_hidden_until_an_upgrade(dynamodb_table):
    plan = Plan(lead_captures_per_month=1)
    leads = LeadsService(limits=plan)
    demo_form(leads)
    leads.capture("demo-request", JANE, visitor("visitor-1"))

    late = leads.capture("demo-request", JANE, visitor("visitor-2"))

    assert late.locked
    page = leads.list_captures(ACCOUNT, CaptureFilters(), limit=10)
    assert len(page.items) == 1 and page.locked_count == 1
    with pytest.raises(LeadsError) as locked:
        leads.get_capture(ACCOUNT, late.capture.capture_id)
    assert locked.value.status_code == 402

    plan.limits.lead_captures_per_month = 0  # upgraded to unlimited
    assert len(leads.list_captures(ACCOUNT, CaptureFilters(), limit=10).items) == 2
    assert leads.get_capture(ACCOUNT, late.capture.capture_id).capture_id == late.capture.capture_id


def test_captures_filter_by_agent_and_form_and_page_newest_first(leads):
    demo_form(leads)
    demo_form(leads, slug="support")
    for index in range(3):
        leads.capture("demo-request", {**JANE, "name": f"Lead {index}"}, visitor())
    other_agent = visitor().model_copy(update={"agent_id": "agent-2"})
    leads.capture("support", JANE, other_agent)

    first_page = leads.list_captures(ACCOUNT, CaptureFilters(agent_id="agent-1"), limit=2)
    second_page = leads.list_captures(ACCOUNT, CaptureFilters(agent_id="agent-1"), limit=2, cursor=first_page.next_cursor)

    names = [capture.answers["name"] for capture in first_page.items + second_page.items]
    assert names == ["Lead 2", "Lead 1", "Lead 0"]
    support = leads.list_captures(ACCOUNT, CaptureFilters(form_slug="support"), limit=10).items
    assert [capture.agent_id for capture in support] == ["agent-2"]


def test_captures_stay_in_their_account(leads):
    demo_form(leads)
    capture = leads.capture("demo-request", JANE, visitor()).capture

    with pytest.raises(LeadsError) as hidden:
        leads.get_capture("another-account", capture.capture_id)
    assert hidden.value.status_code == 404
    assert leads.list_captures("another-account", CaptureFilters(), limit=10).items == []


# Statuses

def test_statuses_are_the_accounts_own(leads):
    demo_form(leads)
    capture = leads.capture("demo-request", JANE, visitor()).capture
    statuses = [LeadStatus(key="fresh", label="Fresh", stage="open"), LeadStatus(key="closed", label="Closed", stage="won")]

    with pytest.raises(LeadsError) as in_use:
        leads.update_settings(ACCOUNT, "owner-1", LeadSettingsRequest(statuses=statuses))
    assert in_use.value.code == "STATUS_IN_USE"

    leads.update_settings(ACCOUNT, "owner-1", LeadSettingsRequest(statuses=statuses, replacements={"new": "fresh"}))

    assert leads.get_capture(ACCOUNT, capture.capture_id).status == "fresh"
    assert leads.update_capture_status(ACCOUNT, capture.capture_id, "closed").status == "closed"
    with pytest.raises(LeadsError):
        leads.update_capture_status(ACCOUNT, capture.capture_id, "won")
    later = leads.capture("demo-request", {**JANE, "name": "Later"}, visitor()).capture
    assert later.status == "fresh", "new captures get the first status"


def test_deleting_a_capture_frees_its_form(leads):
    form = demo_form(leads)
    capture = leads.capture("demo-request", JANE, visitor()).capture

    leads.delete_capture(ACCOUNT, capture.capture_id)

    with pytest.raises(LeadsError):
        leads.get_capture(ACCOUNT, capture.capture_id)
    leads.delete_form(ACCOUNT, form.form_id)


def test_a_racing_duplicate_is_refused_by_the_database(leads):
    """Two calls for the same lead can both pass the read-first check; the guard item decides."""
    demo_form(leads)
    capture = leads.capture("demo-request", JANE, visitor()).capture

    with pytest.raises(DuplicateCapture):
        leads.repository.save_capture(capture)


def test_deleting_a_person_removes_their_personal_accounts_leads(dynamodb_table, monkeypatch):
    from lambdas.account_deletion_handler.handler import AccountDeletionHandler
    from tests.mock_data import TEST_USER_EMAIL, account_for, user_id_for

    monkeypatch.setenv("DYNAMODB_TABLE", dynamodb_table.name)
    monkeypatch.delenv("DYNAMODB_ENDPOINT", raising=False)
    personal = account_for(TEST_USER_EMAIL)
    leads = LeadsService(limits=Plan())
    leads.create_form(personal, "owner-1", CreateLeadFormRequest(slug="demo-request", name="Demo", form_inputs=DEMO_INPUTS))
    leads.capture("demo-request", JANE, visitor().model_copy(update={"account_id": personal}))

    counts = AccountDeletionHandler().delete_user_entities(user_id_for(TEST_USER_EMAIL), TEST_USER_EMAIL)

    assert counts["leads"] == 5, "form, slug guard, capture, capture guard, monthly count"
    assert leads.list_forms(personal) == []
    assert leads.list_captures(personal, CaptureFilters(include_tests=True), limit=10).items == []
