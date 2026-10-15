"""`{{ lead_form:<slug> }}` in agent instructions: the agent sees the form as it is now, or why it can't."""

import pytest

from src.agents.instructions import MAX_MACROS, MacroContext, expand_instructions, macro_arguments
from src.form_models import FormInput, FormInputType, FormInputValidation, FormInputValidationFormat
from src.leads.models import CreateLeadFormRequest
from src.leads.service import LeadsService
from tests.mock_data import LeadsPlan as Plan

ACCOUNT = "acct-1"
WITH_SKILL = MacroContext(ACCOUNT, frozenset({"lead_capture"}))


@pytest.fixture
def form(dynamodb_table):
    return LeadsService(limits=Plan()).create_form(ACCOUNT, "owner-1", CreateLeadFormRequest(
        slug="demo-request",
        name="Demo request",
        purpose="Understand what the visitor needs so sales can follow up.",
        form_inputs=[
            FormInput(input_type=FormInputType.TEXT, name="email", label="Work email",
                      validation=FormInputValidation(format=FormInputValidationFormat.EMAIL),
                      attr={"agent_hint": "Ask only after you have helped them."}),
            FormInput(input_type=FormInputType.SELECT, name="team_size", label="Team size", values=["1-10", "11+"],
                      attr={"optional": "true"}),
            FormInput(input_type=FormInputType.CHOICE, name="consent", label="I agree to be contacted",
                      values=["yes"], attr={"variant": "checkbox"}),
            FormInput(input_type=FormInputType.FILE_UPLOAD, name="brief", label="Project brief",
                      attr={"optional": "true"}),
        ],
    ))


def test_the_macro_becomes_the_form_and_how_to_capture_it(form):
    expanded = expand_instructions("You are Acme's assistant.\n{{ lead_form:demo-request }}", WITH_SKILL)

    assert expanded.startswith("You are Acme's assistant.\n<lead_form slug=\"demo-request\" version=\"1\">")
    assert "Purpose: Understand what the visitor needs" in expanded
    assert "- email (email, required): Work email. Ask only after you have helped them." in expanded
    assert "- team_size (one of: 1-10 | 11+, optional): Team size" in expanded
    assert '- consent (checkbox, "yes" when ticked, required)' in expanded
    assert "brief (file upload; files can't be typed in chat, so ask with render_lead_form" in expanded
    assert 'call capture_lead with form "demo-request"' in expanded
    assert "{{" not in expanded


def test_the_agent_is_told_when_it_cannot_save(form):
    expanded = expand_instructions("{{lead_form:demo-request}}", MacroContext(ACCOUNT, frozenset()))

    assert "<lead_form" in expanded
    assert "cannot save these details" in expanded


def test_missing_and_archived_forms_say_so(form):
    assert expand_instructions("{{ lead_form:nope }}", WITH_SKILL) == '[lead form "nope" not found]'

    LeadsService(limits=Plan()).archive_form(ACCOUNT, form.form_id)

    assert expand_instructions("{{ lead_form:demo-request }}", WITH_SKILL) == '[lead form "demo-request" is not collecting]'


def test_forms_from_another_account_are_not_found(form):
    elsewhere = MacroContext("another-account", frozenset({"lead_capture"}))

    assert "not found" in expand_instructions("{{ lead_form:demo-request }}", elsewhere)


def test_unknown_macros_and_ordinary_braces_are_left_alone(dynamodb_table):
    text = "Use {{ steps.draft.output }} and {{ widget:theme }} and {{ name }}"

    assert expand_instructions(text, WITH_SKILL) == text


def test_only_a_few_macros_are_expanded(dynamodb_table):
    expanded = expand_instructions(" ".join(["{{ lead_form:nope }}"] * (MAX_MACROS + 1)), WITH_SKILL)

    assert expanded.count("not found") == MAX_MACROS
    assert expanded.endswith(f"[lead_form skipped: at most {MAX_MACROS} macros are expanded]")


def test_macro_arguments_lists_the_forms_named():
    assert macro_arguments("{{ lead_form:a-form }} {{ other:x }} {{lead_form:b-form}}", "lead_form") == ["a-form", "b-form"]
