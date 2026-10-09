"""One list of references per resource, read by the validator, the drawing and apply; and `observe`, the one place
each kind writes what it stores back as its spec."""

import pytest
import yaml
from fastapi import BackgroundTasks

from src.blueprints.catalog import example_yaml
from src.blueprints.executor import apply_blueprint
from src.blueprints.export import export_agent
from src.blueprints.kinds import knowledge_base as knowledge_base_kind
from src.blueprints.kinds import kind_for
from src.blueprints.planner import plan_blueprint
from src.blueprints.skills_schema import skill_variants
from src.blueprints.validator import validate_blueprint
from src.config import settings
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from tests.mock_data import TEST_USER_EMAIL

TEAM = example_yaml("agent-team") or ""
SITE_AGENT = example_yaml("site-agent") or ""
SITE_PARAMS = {"site_url": "https://acme.example/about", "business_name": "Acme"}


def references_of(text: str, name: str, params: dict | None = None):
    resources = validate_blueprint(text, params or {}).blueprint.resources
    return kind_for(resources[name].kind).references(name, resources[name])


def test_fields_and_skill_settings_are_references_alike():
    site = {ref.path: ref for ref in references_of(SITE_AGENT, "assistant", SITE_PARAMS)}
    assert site["resources.assistant.knowledge_bases[0]"].kind == "KnowledgeBase"
    assert not site["resources.assistant.knowledge_bases[0]"].may_be_id

    (lead,) = references_of(TEAM, "lead")
    assert (lead.path, lead.target, lead.kind) == ("resources.lead.skills[0].config.target_agent_id", "specialist", "Agent")
    assert lead.may_be_id and lead.outward_wire == "hands work to"


def test_taking_away_is_marked_on_the_reference():
    document = yaml.safe_load(SITE_AGENT)
    document["resources"]["assistant"]["remove_knowledge_bases"] = ["site_kb"]
    document["resources"]["assistant"]["knowledge_bases"] = []
    refs = references_of(yaml.safe_dump(document, sort_keys=False), "assistant", SITE_PARAMS)
    assert [(ref.path, ref.removes) for ref in refs] == [("resources.assistant.remove_knowledge_bases[0]", True)]


def test_a_skill_setting_naming_an_agent_is_marked_in_the_published_schema():
    variant = skill_variants()["agent_invocation"]
    config_model = variant.model.model_fields["config"].annotation
    assert variant.reference_fields == {"target_agent_id": "Agent"}
    assert config_model.model_fields["target_agent_id"].json_schema_extra == {"x-ref-kind": "Agent"}


def test_the_named_agent_comes_first():
    assert validate_blueprint(TEAM, {}).order.index("specialist") < validate_blueprint(TEAM, {}).order.index("lead")


@pytest.fixture
def account(monkeypatch, dynamodb_table) -> None:
    monkeypatch.setattr(knowledge_base_kind, "launch_crawl", lambda *_: None)
    monkeypatch.setattr(settings, "require_pinecone", lambda: None)
    ProviderSettingsRepository().save(
        ProviderSettings(user_email=TEST_USER_EMAIL, provider_name="Bedrock", encrypted_credentials="{}")
    )


def test_every_kind_observes_what_it_built(account):
    validated = validate_blueprint(SITE_AGENT, SITE_PARAMS)
    built = apply_blueprint(validated, plan_blueprint(validated, TEST_USER_EMAIL), TEST_USER_EMAIL, BackgroundTasks())
    exported = yaml.safe_load(export_agent(built.resources["assistant"].id, TEST_USER_EMAIL) or "")

    resources = exported["resources"]
    assert list(resources) == ["knowledge", "agent", "widget"]
    assert {name: resource["id"] for name, resource in resources.items()} == {
        "knowledge": built.resources["site_kb"].id,
        "agent": built.resources["assistant"].id,
        "widget": built.resources["widget"].id,
    }
    assert resources["agent"]["knowledge_bases"] == ["knowledge"]
    assert resources["widget"]["agent"] == "agent"
    assert resources["knowledge"]["crawl"]["url"] == "https://acme.example/about"
    assert exported["outputs"]["snippet"]["value"] == "{{ resources.widget.snippet }}"

    # Written back as it is, nothing changes.
    replanned = plan_blueprint(validate_blueprint(yaml.safe_dump(exported, sort_keys=False), {}), TEST_USER_EMAIL)
    assert {step.action for step in replanned.steps} == {"unchanged"}
