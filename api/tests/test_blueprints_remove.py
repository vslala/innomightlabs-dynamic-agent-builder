"""Removing through a blueprint: always explicit, run after everything else, and done once."""

import pytest
import yaml
from fastapi import BackgroundTasks

from src.agents.repository import AgentRepository
from src.apikeys.repository import ApiKeyRepository
from src.blueprints.approval import approval_form
from src.blueprints.catalog import example_yaml
from src.blueprints.executor import apply_blueprint
from src.blueprints.export import export_agent
from src.blueprints.issues import BlueprintInvalid
from src.blueprints.kinds import knowledge_base as knowledge_base_kind
from src.blueprints.kinds.agent import UnlinkKnowledgeBase
from src.blueprints.kinds.knowledge_base import DeleteKnowledgeBase
from src.blueprints.models import DeploymentStatus
from src.blueprints.planner import plan_blueprint
from src.blueprints.validator import validate_blueprint
from src.builder.canvas import drawing_for, render_drawing
from src.config import settings
from src.knowledge.models import KnowledgeBase, KnowledgeBaseStatus
from src.knowledge.repository import AgentKnowledgeBaseRepository, KnowledgeBaseRepository
from src.knowledge.service import KnowledgeBaseService
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from src.skills.repository import AgentSkillRepository
from tests.mock_data import TEST_USER_EMAIL

SITE_AGENT = example_yaml("site-agent") or ""
PARAMS = {"site_url": "https://acme.example", "business_name": "Acme"}


@pytest.fixture(autouse=True)
def account(monkeypatch, dynamodb_table) -> None:
    monkeypatch.setattr(knowledge_base_kind, "launch_crawl", lambda job_id, *_: None)
    monkeypatch.setattr(settings, "require_pinecone", lambda: None)
    monkeypatch.setattr(KnowledgeBaseService, "_delete_pinecone_namespace", lambda self, kb_id: 0)
    ProviderSettingsRepository().save(
        ProviderSettings(user_email=TEST_USER_EMAIL, provider_name="Bedrock", encrypted_credentials="{}")
    )


def build(text: str, params: dict | None = None):
    validated = validate_blueprint(text, PARAMS if params is None else params)
    plan = plan_blueprint(validated, TEST_USER_EMAIL)
    assert plan.ok, plan.blockers
    return validated, plan, apply_blueprint(validated, plan, TEST_USER_EMAIL, BackgroundTasks())


def agent_with_two_knowledge_bases() -> tuple[str, str, str]:
    """The site agent, plus a second knowledge base linked from the dashboard. Returns agent, site KB, docs KB."""
    _, _, built = build(SITE_AGENT)
    agent_id = built.resources["assistant"].id
    docs = KnowledgeBaseRepository().save(KnowledgeBase(name="Innomight Website docs", created_by=TEST_USER_EMAIL))
    AgentKnowledgeBaseRepository().link(agent_id, docs.kb_id, TEST_USER_EMAIL)
    return agent_id, built.resources["site_kb"].id, docs.kb_id


def exported(agent_id: str) -> dict:
    return yaml.safe_load(export_agent(agent_id, TEST_USER_EMAIL) or "")


def kb_named(document: dict, kb_id: str) -> str:
    return next(name for name, spec in document["resources"].items() if spec.get("id") == kb_id)


def linked(agent_id: str) -> set[str]:
    return {link.kb_id for link in AgentKnowledgeBaseRepository().find_kbs_for_agent(agent_id)}


def test_disconnecting_a_knowledge_base_keeps_it_and_the_other(dynamodb_table):
    agent_id, site_kb, docs_kb = agent_with_two_knowledge_bases()
    document = exported(agent_id)
    docs_name = kb_named(document, docs_kb)
    agent = document["resources"]["agent"]
    agent["knowledge_bases"].remove(docs_name)
    agent["remove_knowledge_bases"] = [docs_name]
    text = yaml.safe_dump(document, sort_keys=False)

    validated, plan, applied = build(text, {})
    step = next(step for step in plan.steps if step.resource == "agent")
    assert step.action == "update"
    assert step.removals == ["disconnect knowledge base 'Innomight Website docs'"]
    assert applied.status == DeploymentStatus.APPLIED
    assert applied.removed == step.removals
    assert linked(agent_id) == {site_kb}
    assert KnowledgeBaseRepository().find_by_id(docs_kb, TEST_USER_EMAIL).status != KnowledgeBaseStatus.DELETED

    # Done once: the same blueprint again changes nothing.
    _, again, _ = build(text, {})
    assert not again.changes_anything


def test_uninstalling_a_skill(dynamodb_table):
    _, _, built = build(SITE_AGENT)
    agent_id = built.resources["assistant"].id
    document = exported(agent_id)
    document["resources"]["agent"]["skills"] = []
    document["resources"]["agent"]["remove_skills"] = ["lead_capture"]
    text = yaml.safe_dump(document, sort_keys=False)

    _, plan, applied = build(text, {})
    assert plan.removals == ["uninstall skill lead capture"]
    assert AgentSkillRepository().list_by_agent(agent_id) == []
    _, again, _ = build(text, {})
    assert not again.changes_anything


def test_leaving_things_out_still_removes_nothing(dynamodb_table):
    agent_id, site_kb, docs_kb = agent_with_two_knowledge_bases()
    document = exported(agent_id)
    agent = document["resources"]["agent"]
    agent["knowledge_bases"] = [kb_named(document, site_kb)]
    agent["skills"] = []
    _, plan, _ = build(yaml.safe_dump(document, sort_keys=False), {})
    assert plan.removals == []
    assert linked(agent_id) == {site_kb, docs_kb}
    assert len(AgentSkillRepository().list_by_agent(agent_id)) == 1


def test_deleting_resources_runs_last_and_dependents_first(dynamodb_table):
    _, _, built = build(SITE_AGENT)
    agent_id, kb_id = built.resources["assistant"].id, built.resources["site_kb"].id
    document = exported(agent_id)
    for spec in document["resources"].values():
        spec["remove"] = True
    document["outputs"] = {}
    text = yaml.safe_dump(document, sort_keys=False)

    _, plan, applied = build(text, {})
    assert {step.action for step in plan.steps} == {"remove"}
    assert applied.status == DeploymentStatus.APPLIED
    assert [line.split(":")[0] for line in applied.removed] == [
        "delete chat widget 'Acme assistant widget'",
        "delete agent 'Acme assistant'",
        "delete knowledge base 'Acme website'",
    ]
    assert AgentRepository().find_agent_by_id(agent_id, TEST_USER_EMAIL) is None
    assert ApiKeyRepository().find_all_by_agent(agent_id) == []
    assert KnowledgeBaseRepository().find_by_id(kb_id, TEST_USER_EMAIL).status == KnowledgeBaseStatus.DELETED

    # Already gone counts as done.
    _, again, _ = build(text, {})
    assert {step.action for step in again.steps} == {"unchanged"}
    assert again.ok


def test_removing_needs_an_id():
    text = SITE_AGENT.replace("  widget:\n    kind: WidgetKey\n", "  widget:\n    kind: WidgetKey\n    remove: true\n")
    with pytest.raises(BlueprintInvalid) as raised:
        validate_blueprint(text, PARAMS)
    assert "resources.widget.remove" in {issue.path for issue in raised.value.issues}


def test_nothing_that_stays_can_use_what_is_removed():
    text = SITE_AGENT.replace("  site_kb:\n    kind: KnowledgeBase\n", "  site_kb:\n    kind: KnowledgeBase\n    id: kb-1\n    remove: true\n")
    with pytest.raises(BlueprintInvalid) as raised:
        validate_blueprint(text, PARAMS)
    paths = {issue.path for issue in raised.value.issues}
    assert "resources.assistant.knowledge_bases[0]" in paths
    assert "outputs.crawl_job_id.value" in paths


def test_a_contradiction_is_an_issue():
    text = SITE_AGENT.replace(
        "    knowledge_bases: [site_kb]\n",
        "    knowledge_bases: [site_kb]\n    remove_knowledge_bases: [site_kb]\n    remove_skills: [lead_capture, lead_captur]\n",
    )
    with pytest.raises(BlueprintInvalid) as raised:
        validate_blueprint(text, PARAMS)
    messages = {issue.path: issue for issue in raised.value.issues}
    assert "resources.assistant.remove_knowledge_bases[0]" in messages
    assert "resources.assistant.remove_skills[0]" in messages
    assert messages["resources.assistant.remove_skills[1]"].hint == "Did you mean 'lead_capture'?"


def test_a_failed_disconnect_puts_everything_back(dynamodb_table, monkeypatch):
    """Disconnecting can be undone, so it runs before the commit point, and a failure undoes the whole apply."""
    agent_id, site_kb, docs_kb = agent_with_two_knowledge_bases()
    document = exported(agent_id)
    docs_name = kb_named(document, docs_kb)
    agent = document["resources"]["agent"]
    agent["knowledge_bases"].remove(docs_name)
    agent["remove_knowledge_bases"] = [docs_name]
    agent["instructions"] += "\nMention the opening hours."

    def fail(*args, **kwargs):
        raise RuntimeError("links table down")

    monkeypatch.setattr(UnlinkKnowledgeBase, "run", fail)
    _, _, applied = build(yaml.safe_dump(document, sort_keys=False), {})
    assert applied.status == DeploymentStatus.FAILED
    assert applied.removed == []
    assert "opening hours" not in AgentRepository().find_agent_by_id(agent_id, TEST_USER_EMAIL).agent_persona
    assert linked(agent_id) == {site_kb, docs_kb}


def test_a_failed_delete_keeps_the_rest_and_says_so(dynamodb_table, monkeypatch):
    """Deleting can't be undone, so it runs after the commit point; a failure there leaves the rest applied."""
    _, _, built = build(SITE_AGENT)
    agent_id = built.resources["assistant"].id
    document = exported(agent_id)
    document["resources"]["agent"]["instructions"] += "\nMention the opening hours."
    document["resources"]["agent"]["knowledge_bases"] = []
    document["resources"]["knowledge"]["remove"] = True
    document["outputs"].pop("crawl_job_id", None)

    def fail(*args, **kwargs):
        raise RuntimeError("vector store down")

    monkeypatch.setattr(DeleteKnowledgeBase, "run", fail)
    _, _, applied = build(yaml.safe_dump(document, sort_keys=False), {})
    assert applied.status == DeploymentStatus.FAILED_PARTIAL
    assert "didn't finish: vector store down" in applied.error
    assert "opening hours" in AgentRepository().find_agent_by_id(agent_id, TEST_USER_EMAIL).agent_persona


def test_the_approval_and_the_drawing_call_out_removals(dynamodb_table):
    agent_id, _, docs_kb = agent_with_two_knowledge_bases()
    document = exported(agent_id)
    docs_name = kb_named(document, docs_kb)
    document["resources"]["agent"]["knowledge_bases"].remove(docs_name)
    document["resources"]["agent"]["remove_knowledge_bases"] = [docs_name]
    validated = validate_blueprint(yaml.safe_dump(document, sort_keys=False), {})
    plan = plan_blueprint(validated, TEST_USER_EMAIL)

    help_text = approval_form("p1", plan, {})["form"]["form_inputs"][0]["attr"]["help_text"]
    assert "This removes, and it can't be undone:\n- disconnect knowledge base 'Innomight Website docs'" in help_text
    html = render_drawing(drawing_for(validated, plan, stage="plan", plan_id="p1"))
    assert '<ul class="removals">' in html
    assert "disconnect knowledge base &#39;Innomight Website docs&#39;" in html
