"""Automations in blueprints: a trigger and steps, built with the form and agent they act on."""

import pytest

from src.agents.repository import AgentRepository
from src.automations.models import AutomationNode, AutomationNodeType, AutomationStatus, AutomationTriggerType
from src.automations.repository import AutomationRepository
from src.automations.smart_values import SmartValueResolver
from fastapi import BackgroundTasks

from src.blueprints import service as blueprints_service
from src.blueprints.executor import apply_blueprint
from src.blueprints.models import DeploymentStatus
from src.blueprints.planner import plan_blueprint
from src.blueprints.validator import validate_blueprint
from src.blueprints.catalog import example_yaml
from src.blueprints.kinds.automation import read_chain
from src.blueprints.kinds.base import Action
from src.leads.service import CaptureOrigin, LeadsService
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from src.skills.models import ActorKind
from tests.mock_data import LeadsPlan, TEST_USER_EMAIL, account_for
from tests.mock_data import test_owner as _test_owner

OWNER = _test_owner()

BLUEPRINT = """
apiVersion: innomight/v2
kind: Blueprint
metadata: {name: lead-desk, title: Lead desk}
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
    instructions: "Help visitors. {{ lead_form:demo-request }}"
    skills:
      - id: lead_capture
        available_to: [visitor, guest]
  tell_sales:
    kind: Automation
    title: Tell sales
    enabled: true
    trigger:
      lead_captured:
        form: demo_request
        agent: desk
    skills:
      - id: send_email
        config: {to: sales@acme.example}
    steps:
      - name: summarise
        agent: desk
        prompt: "Summarise this lead in one line: {{ trigger.lead.answers.email }}"
      - name: email_sales
        skill: send_email
        action: send
        arguments:
          subject: "New lead: {{ trigger.lead.answers.email }}"
          body: "{{ steps.summarise.output.response_text }}"
"""


@pytest.fixture(autouse=True)
def bedrock(dynamodb_table) -> None:
    ProviderSettingsRepository().save(
        ProviderSettings(account_id=account_for(TEST_USER_EMAIL), provider_name="Bedrock", encrypted_credentials="{}")
    )


def deploy(text: str = BLUEPRINT, params: dict | None = None):
    return blueprints_service.deploy_blueprint(text, params or {}, OWNER)


def issues_of(outcome) -> list[str]:
    found = outcome.issues if isinstance(outcome, blueprints_service.Invalid) else outcome.plan.blockers
    return [f"{issue.path}: {issue.message}" for issue in found]


def the_automation(title: str = "Tell sales"):
    [found] = [item for item in AutomationRepository().list_in_account(OWNER.account_id) if item.title == title]
    return found


def actions(deployed) -> dict[str, Action]:
    return {step.resource: step.action for step in deployed.plan.steps}


def test_a_form_an_agent_and_the_automation_that_acts_on_its_leads_deploy_together():
    deployed = deploy()

    assert isinstance(deployed, blueprints_service.Deployed), issues_of(deployed)
    assert [step.resource for step in deployed.plan.steps] == ["demo_request", "desk", "tell_sales"]
    automation = the_automation()
    assert automation.status == AutomationStatus.ACTIVE
    chain = read_chain(*AutomationRepository().get_graph(automation.automation_id))
    assert chain is not None
    assert [node.alias for node in chain.steps] == ["summarise", "email_sales"]
    assert chain.steps[0].config["prompt_template"].startswith("Summarise this lead")
    assert chain.steps[1].config["skill_id"] == "send_email"
    assert chain.trigger.type == AutomationTriggerType.LEAD_CAPTURED
    assert chain.trigger.config["form_slug"] == "demo-request", "the resource name is the form's slug, hyphenated"
    assert chain.trigger.config["agent_id"] == chain.steps[0].config["agent_id"], "the agent this blueprint built"


def test_a_captured_lead_runs_what_the_blueprint_built(monkeypatch):
    started: list[str] = []
    monkeypatch.setattr("src.automations.dispatch.invoke_automation_run_async",
                        lambda run_id, automation_id, owner: started.append(run_id))
    deploy()
    agent = AgentRepository().find_by_name(OWNER.account_id, OWNER.user_id, "Demo desk")
    origin = CaptureOrigin(account_id=OWNER.account_id, agent_id=agent.agent_id, actor_kind=ActorKind.VISITOR,
                           actor_id="visitor-1")

    LeadsService(limits=LeadsPlan()).capture("demo-request", {"email": "jane@acme.com"}, origin)

    [run_id] = started
    run = AutomationRepository().find_run_by_id(run_id)
    assert SmartValueResolver(run.context).render_template(
        "{{ trigger.lead.answers.email }} on {{ trigger.lead.form_slug }}"
    ) == "jane@acme.com on demo-request"


def test_deploying_again_changes_nothing():
    deploy()

    again = deploy()

    assert actions(again) == {"demo_request": Action.UNCHANGED, "desk": Action.UNCHANGED, "tell_sales": Action.UNCHANGED}


def test_changing_a_step_updates_the_automation_and_keeps_the_others_ids():
    deploy()
    before = read_chain(*AutomationRepository().get_graph(the_automation().automation_id))

    updated = deploy(BLUEPRINT.replace("Summarise this lead in one line", "Summarise this lead in two lines"))

    assert actions(updated)["tell_sales"] == Action.UPDATE
    after = read_chain(*AutomationRepository().get_graph(the_automation().automation_id))
    assert after.steps[0].config["prompt_template"].startswith("Summarise this lead in two lines")
    assert [node.node_id for node in after.steps] == [node.node_id for node in before.steps]
    assert after.trigger.trigger_id == before.trigger.trigger_id
    assert the_automation().status == AutomationStatus.ACTIVE


def test_turning_it_off_and_on():
    deploy()

    off = deploy(BLUEPRINT.replace("enabled: true", "enabled: false"))
    assert actions(off)["tell_sales"] == Action.UPDATE and the_automation().status == AutomationStatus.DISABLED

    on = deploy(BLUEPRINT)
    assert actions(on)["tell_sales"] == Action.UPDATE and the_automation().status == AutomationStatus.ACTIVE


def test_a_draft_is_saved_but_not_listening(monkeypatch):
    started: list[str] = []
    monkeypatch.setattr("src.automations.dispatch.invoke_automation_run_async",
                        lambda run_id, automation_id, owner: started.append(run_id))

    deploy(BLUEPRINT.replace("    enabled: true\n", ""))

    assert the_automation().status == AutomationStatus.DRAFT


def test_it_can_run_on_a_schedule():
    schedule = BLUEPRINT.replace(
        "      lead_captured:\n        form: demo_request\n        agent: desk\n",
        "      schedule:\n        cron: \"0 9 * * 1\"\n        timezone: Europe/London\n",
    ).replace("{{ trigger.lead.answers.email }}", "{{ input.topic }}")

    deployed = deploy(schedule)

    assert isinstance(deployed, blueprints_service.Deployed), issues_of(deployed)
    chain = read_chain(*AutomationRepository().get_graph(the_automation().automation_id))
    assert chain.trigger.type == AutomationTriggerType.SCHEDULE
    assert chain.trigger.config["cron_expression"] == "0 9 * * 1"


@pytest.mark.parametrize(("change", "message"), [
    ("name: email_sales", "name: summarise"),
    ("body: \"{{ steps.summarise.output.response_text }}\"", "body: \"{{ steps.later.output }}\""),
    ("action: send", "action: no_such_action"),
    ("        skill: send_email\n", "        skill: aws_cli\n"),
])
def test_step_mistakes_are_caught_before_anything_is_built(change, message):
    invalid = deploy(BLUEPRINT.replace(change, message))

    assert isinstance(invalid, blueprints_service.Invalid), "nothing was planned"


def test_a_step_may_not_read_a_step_below_it():
    invalid = deploy(BLUEPRINT.replace("{{ trigger.lead.answers.email }}\"\n      - name: email_sales",
                                       "{{ steps.email_sales.output }}\"\n      - name: email_sales"))

    assert isinstance(invalid, blueprints_service.Invalid)
    assert any("isn't a step before it" in issue for issue in issues_of(invalid))


def test_a_trigger_names_exactly_one_start():
    invalid = deploy(BLUEPRINT.replace("    trigger:\n      lead_captured:", "    trigger:\n      manual: {}\n      lead_captured:"))

    assert isinstance(invalid, blueprints_service.Invalid)
    assert any("exactly one" in issue for issue in issues_of(invalid))


def test_smart_values_belong_in_steps_only():
    invalid = deploy(BLUEPRINT.replace("title: Tell sales", 'title: "Tell {{ trigger.lead.answers.email }}"'))

    assert isinstance(invalid, blueprints_service.Invalid)
    assert any("isn't something a blueprint can fill in" in issue for issue in issues_of(invalid))


def test_a_trigger_for_a_form_that_exists_nowhere_blocks_the_plan():
    blocked = deploy(BLUEPRINT.replace("form: demo_request", "form: no_such_form"))

    assert isinstance(blocked, blueprints_service.Blocked)
    assert any("no lead form 'no_such_form'" in issue for issue in issues_of(blocked))


def test_an_automation_with_branches_is_left_alone():
    deploy()
    automation = the_automation()
    # The dashboard's own editor adds a condition
    repository = AutomationRepository()
    nodes, edges, triggers = repository.get_graph(automation.automation_id)
    repository.save_graph(automation.automation_id, [
        *nodes,
        AutomationNode(automation_id=automation.automation_id, type=AutomationNodeType.CONDITION, name="Check",
                       config={"expression": "true"}),
    ], edges, triggers)

    blocked = deploy(BLUEPRINT.replace("Summarise this lead", "Sum up this lead"))

    assert isinstance(blocked, blueprints_service.Blocked)
    assert any("can't change it" in issue for issue in issues_of(blocked))


def test_the_recipe_alerts_sales_from_an_automation():
    recipe = (example_yaml("lead-qualifier") or "").replace(
        "      - id: send_email\n", "      - id: send_email\n        config: {to: sales@acme.example}\n"
    )

    deployed = deploy(recipe, {"site_url": "https://acme.example", "business_name": "Acme"})

    steps = {step.resource: step for step in deployed.plan.steps}
    assert steps["alert_sales"].kind == "Automation", issues_of(deployed)


def test_a_failure_while_building_the_automation_undoes_everything(monkeypatch):
    """The last thing applied is turning it on; if that fails, the form, agent and automation all go."""
    def refuse(*args, **kwargs):
        raise RuntimeError("scheduler down")

    monkeypatch.setattr("src.blueprints.kinds.automation.SetAutomationStatus.run", refuse)
    validated = validate_blueprint(BLUEPRINT, {})
    plan = plan_blueprint(validated, OWNER)

    deployment = apply_blueprint(validated, plan, OWNER, BackgroundTasks())

    assert deployment.status == DeploymentStatus.FAILED and deployment.error == "scheduler down"
    assert [item for item in AutomationRepository().list_in_account(OWNER.account_id)] == []
    assert LeadsService().repository.find_form_by_slug(OWNER.account_id, "demo-request") is None
    assert AgentRepository().find_by_name(OWNER.account_id, OWNER.user_id, "Demo desk") is None


def test_leaving_the_automation_out_removes_it():
    first = deploy()
    assert isinstance(first, blueprints_service.Deployed)
    kit_id = first.kit.kit_id
    smaller = BLUEPRINT.split("  tell_sales:")[0]

    removed = blueprints_service.deploy_blueprint(smaller, {}, OWNER, kit_id=kit_id)

    assert isinstance(removed, blueprints_service.Deployed), issues_of(removed)
    assert AutomationRepository().list_in_account(OWNER.account_id) == []
