"""Lead forms in blueprints: Ila builds a form and the agent whose instructions name it, in one plan."""

import pytest

from src.agents.repository import AgentRepository
from src.blueprints import service as blueprints_service
from src.blueprints.catalog import example_yaml
from src.blueprints.kinds.base import Action
from src.form_models import FormInput, FormInputType
from src.leads.models import CreateLeadFormRequest
from src.leads.service import LeadsService
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from tests.mock_data import TEST_USER_EMAIL, account_for
from tests.mock_data import test_owner as _test_owner

OWNER = _test_owner()

BLUEPRINT = """
apiVersion: innomight/v2
kind: Blueprint
metadata: {name: demo-desk, title: Demo desk}
resources:
  demo_request:
    kind: LeadForm
    name: Demo request
    form_inputs:
      - {input_type: text, name: email, label: Work email, validation: {format: email}}
  desk:
    kind: Agent
    name: Demo desk
    provider: Bedrock
    instructions: |
      Help visitors, then: {{ lead_form:demo-request }}
    skills:
      - id: lead_capture
        available_to: [visitor, guest]
"""


@pytest.fixture(autouse=True)
def bedrock(dynamodb_table) -> None:
    ProviderSettingsRepository().save(
        ProviderSettings(account_id=account_for(TEST_USER_EMAIL), provider_name="Bedrock", encrypted_credentials="{}")
    )


def deploy(text: str, params: dict | None = None):
    return blueprints_service.deploy_blueprint(text, params or {}, OWNER)


def issues_of(outcome) -> list[str]:
    found = outcome.issues if isinstance(outcome, blueprints_service.Invalid) else outcome.plan.blockers
    return [f"{issue.path}: {issue.message}" for issue in found]


def test_a_form_and_the_agent_that_collects_it_deploy_together():
    deployed = deploy(BLUEPRINT)

    assert isinstance(deployed, blueprints_service.Deployed), issues_of(deployed)
    assert [step.resource for step in deployed.plan.steps] == ["demo_request", "desk"], "the form first"
    form = LeadsService().repository.find_form_by_slug(OWNER.account_id, "demo-request")
    assert form is not None and form.name == "Demo request"
    assert form.form_inputs[0].validation.max_length == 2000, "stored with the lead defaults"
    agent = AgentRepository().find_by_name(OWNER.account_id, OWNER.user_id, "Demo desk")
    assert "{{ lead_form:demo-request }}" in agent.agent_persona, "the macro is kept for the agent to expand"


def test_deploying_again_changes_nothing_and_a_new_field_is_a_new_version():
    deploy(BLUEPRINT)

    again = deploy(BLUEPRINT)
    assert {step.resource: step.action for step in again.plan.steps}["demo_request"] == Action.UNCHANGED

    with_company = BLUEPRINT.replace(
        "      - {input_type: text, name: email",
        "      - {input_type: text, name: company, label: Company}\n      - {input_type: text, name: email",
    )
    updated = deploy(with_company)
    assert {step.resource: step.action for step in updated.plan.steps}["demo_request"] == Action.UPDATE
    assert LeadsService().repository.find_form_by_slug(OWNER.account_id, "demo-request").version == 2


def test_an_agent_may_name_a_form_the_account_already_has():
    LeadsService().create_form(OWNER.account_id, OWNER.user_id, CreateLeadFormRequest(
        slug="existing-form", name="Existing", form_inputs=[FormInput(input_type=FormInputType.TEXT, name="n", label="N")]
    ))
    only_agent = BLUEPRINT.split("  desk:")[0].split("resources:")[0] + "resources:\n  desk:" + BLUEPRINT.split("  desk:")[1]

    deployed = deploy(only_agent.replace("demo-request", "existing-form"))

    assert isinstance(deployed, blueprints_service.Deployed), issues_of(deployed)


def test_a_form_that_exists_nowhere_blocks_the_plan():
    blocked = deploy(BLUEPRINT.replace("{{ lead_form:demo-request }}", "{{ lead_form:no-such-form }}"))

    assert isinstance(blocked, blueprints_service.Blocked)
    assert any("no lead form 'no-such-form'" in issue for issue in issues_of(blocked))


def test_macros_belong_in_instructions_only():
    invalid = deploy(BLUEPRINT.replace("name: Demo desk", 'name: "Desk {{ lead_form:demo-request }}"'))

    assert isinstance(invalid, blueprints_service.Invalid)
    assert any("only works in an agent's `instructions`" in issue for issue in issues_of(invalid))


def test_a_form_must_be_one_visitors_can_be_shown():
    invalid = deploy(BLUEPRINT.replace("input_type: text, name: email", "input_type: password, name: email"))

    assert isinstance(invalid, blueprints_service.Invalid)
    assert any(issue.startswith("resources.demo_request.form_inputs") and "can't be shown to visitors" in issue
               for issue in issues_of(invalid))


def test_the_plan_counts_new_forms_against_the_plan():
    LeadsService().create_form(OWNER.account_id, OWNER.user_id, CreateLeadFormRequest(
        slug="first-form", name="First", form_inputs=[FormInput(input_type=FormInputType.TEXT, name="n", label="N")]
    ))

    blocked = deploy(BLUEPRINT)

    assert isinstance(blocked, blueprints_service.Blocked), "the free plan has one active form"
    assert any("1 active lead form" in issue for issue in issues_of(blocked))


def test_the_lead_qualifier_recipe_uses_a_lead_form():
    # The recipe leaves the sales team's address for the person to give; give it here
    recipe = (example_yaml("lead-qualifier") or "").replace(
        "      - id: send_email\n", "      - id: send_email\n        config: {to: sales@acme.example}\n"
    )
    deployed = deploy(recipe, {"site_url": "https://acme.example", "business_name": "Acme"})

    assert isinstance(deployed, blueprints_service.Blocked | blueprints_service.Deployed), issues_of(deployed)
    steps = {step.resource: step for step in deployed.plan.steps}
    assert steps["sales_lead"].kind == "LeadForm"
