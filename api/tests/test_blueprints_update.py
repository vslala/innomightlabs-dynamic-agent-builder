"""Applying a blueprint again updates what it built instead of building it twice."""

import pytest
import yaml
from fastapi import BackgroundTasks

from src.agents.repository import AgentRepository
from src.apikeys.repository import ApiKeyRepository
from src.blueprints.catalog import example_yaml
from src.blueprints.executor import apply_blueprint
from src.blueprints.export import export_agent, with_ids
from src.blueprints.kinds import knowledge_base as knowledge_base_kind
from src.blueprints.kinds.widget_key import WidgetKeyKind
from src.blueprints.models import DeploymentStatus
from src.blueprints.planner import plan_blueprint
from src.blueprints.validator import validate_blueprint
from src.config import settings
from src.knowledge.repository import KnowledgeBaseRepository
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from src.skills.models import ActorKind
from src.skills.repository import AgentSkillRepository
from tests.mock_data import TEST_USER_EMAIL

SITE_AGENT = example_yaml("site-agent") or ""
DOCS = example_yaml("docs-assistant") or ""
PARAMS = {"site_url": "https://acme.example", "business_name": "Acme"}


@pytest.fixture
def launched(monkeypatch, dynamodb_table) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(knowledge_base_kind, "launch_crawl", lambda job_id, *_: calls.append(job_id))
    monkeypatch.setattr(settings, "require_pinecone", lambda: None)
    # Superuser: the free tier's single agent would otherwise block the second build in some tests.
    monkeypatch.setattr(settings, "is_superuser_email", lambda email: True)
    ProviderSettingsRepository().save(
        ProviderSettings(user_email=TEST_USER_EMAIL, provider_name="Bedrock", encrypted_credentials="{}")
    )
    return calls


def build(text: str = SITE_AGENT, params: dict | None = None):
    validated = validate_blueprint(text, PARAMS if params is None else params)
    plan = plan_blueprint(validated, TEST_USER_EMAIL)
    assert plan.ok, plan.blockers
    return plan, apply_blueprint(validated, plan, TEST_USER_EMAIL, BackgroundTasks())


def counts() -> tuple[int, int]:
    return (
        len(AgentRepository().find_all_by_created_by(TEST_USER_EMAIL)),
        len(KnowledgeBaseRepository().find_all_by_user(TEST_USER_EMAIL)),
    )


def test_applying_the_same_blueprint_twice_changes_nothing(launched):
    _, first = build()
    plan, second = build()

    assert [step.action for step in plan.steps] == ["unchanged", "unchanged", "unchanged"]
    assert second.status == DeploymentStatus.APPLIED
    assert {name: r.id for name, r in second.resources.items()} == {name: r.id for name, r in first.resources.items()}
    assert counts() == (1, 1)
    assert len(launched) == 1  # the website isn't read again
    # Outputs still resolve for kept resources.
    assert first.outputs["snippet"].value == second.outputs["snippet"].value


def test_an_edited_blueprint_updates_the_same_resources(launched):
    _, first = build()
    agent_id = first.resources["assistant"].id
    key = ApiKeyRepository().find_all_by_agent(agent_id)[0]

    edited = SITE_AGENT.replace(
        "keep answers short and friendly.", "keep answers short and friendly. Always mention the opening hours."
    ).replace("allow_guests: true", "allow_guests: false").replace(
        "      - id: lead_capture\n        available_to: [visitor, guest]",
        "      - id: lead_capture\n        available_to: [visitor, guest]\n      - id: html_canvas",
    )
    plan, second = build(edited)

    actions = {step.resource: (step.action, step.changes) for step in plan.steps}
    assert actions["site_kb"] == ("unchanged", [])
    assert actions["assistant"][0] == "update"
    assert set(actions["assistant"][1]) == {"update its instructions", "add skill html canvas"}
    assert actions["widget"] == ("update", ["ask visitors to sign in"])

    assert second.resources["assistant"].id == agent_id
    agent = AgentRepository().find_agent_by_id(agent_id, TEST_USER_EMAIL)
    assert "opening hours" in agent.agent_persona
    assert {skill.skill_id for skill in AgentSkillRepository().list_by_agent(agent_id)} == {"lead_capture", "html_canvas"}
    [updated_key] = ApiKeyRepository().find_all_by_agent(agent_id)
    assert updated_key.key_id == key.key_id
    assert updated_key.public_key == key.public_key  # the snippet on the site keeps working
    assert updated_key.allow_guests is False
    assert counts() == (1, 1)
    assert len(launched) == 1


def test_changing_the_crawl_reads_the_site_again(launched):
    build()
    plan, _ = build(SITE_AGENT.replace("max_pages: 10", "max_pages: 5"))

    assert plan.steps[0].action == "update"
    assert plan.steps[0].changes == ["read https://acme.example again, up to 5 pages"]
    assert len(launched) == 2
    assert counts() == (1, 1)


def test_a_failed_update_puts_things_back(launched, monkeypatch):
    _, first = build()
    agent_id = first.resources["assistant"].id
    before = AgentRepository().find_agent_by_id(agent_id, TEST_USER_EMAIL).agent_persona

    def fail(*args, **kwargs):
        raise RuntimeError("key service down")

    monkeypatch.setattr(WidgetKeyKind, "update", fail)
    edited = SITE_AGENT.replace("keep answers short and friendly.", "be terse.").replace(
        "allow_guests: true", "allow_guests: false"
    ).replace(
        "      - id: lead_capture\n        available_to: [visitor, guest]",
        "      - id: lead_capture\n        available_to: [visitor]\n      - id: html_canvas",
    )
    _, failed = build(edited)

    assert failed.status == DeploymentStatus.FAILED
    assert AgentRepository().find_agent_by_id(agent_id, TEST_USER_EMAIL).agent_persona == before
    skills = {skill.skill_id: skill for skill in AgentSkillRepository().list_by_agent(agent_id)}
    assert set(skills) == {"lead_capture"}
    assert set(skills["lead_capture"].available_to) == {ActorKind.OWNER, ActorKind.VISITOR, ActorKind.GUEST}


def test_an_unknown_id_blocks(launched):
    text = SITE_AGENT.replace("    kind: Agent\n", "    kind: Agent\n    id: not-mine\n")
    validated = validate_blueprint(text, PARAMS)
    plan = plan_blueprint(validated, TEST_USER_EMAIL)
    assert any(issue.path == "resources.assistant.id" for issue in plan.blockers)


def test_an_exported_agent_plans_as_unchanged_and_can_be_extended(launched):
    docs_params = {"docs_url": "https://docs.acme.example", "product_name": "Acme"}
    _, built = build(DOCS, docs_params)
    agent_id = built.resources["docs_assistant"].id

    exported = export_agent(agent_id, TEST_USER_EMAIL)
    assert exported is not None
    validated = validate_blueprint(exported, {})
    plan = plan_blueprint(validated, TEST_USER_EMAIL)
    assert plan.ok, plan.blockers
    assert [step.action for step in plan.steps] == ["unchanged", "unchanged"]

    # Give the docs assistant a widget: the only new thing is the widget.
    document = yaml.safe_load(exported)
    document["resources"]["widget"] = {
        "kind": "WidgetKey", "agent": "agent", "allowed_origins": ["https://docs.acme.example"],
    }
    plan, applied = build(yaml.safe_dump(document, sort_keys=False), {})
    assert [(step.resource, step.action) for step in plan.steps] == [
        ("knowledge", "unchanged"), ("agent", "unchanged"), ("widget", "create"),
    ]
    assert applied.resources["agent"].id == agent_id
    assert len(ApiKeyRepository().find_all_by_agent(agent_id)) == 1
    assert counts() == (1, 1)


def test_with_ids_pins_each_resource():
    pinned = yaml.safe_load(with_ids(SITE_AGENT, {"assistant": "agent-1", "widget": "key-1"}))
    assert list(pinned["resources"]["assistant"])[:2] == ["kind", "id"]
    assert pinned["resources"]["assistant"]["id"] == "agent-1"
    assert "id" not in pinned["resources"]["site_kb"]
