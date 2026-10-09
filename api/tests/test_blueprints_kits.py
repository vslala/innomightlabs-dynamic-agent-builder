"""Kits: everything a blueprint built, as one thing with versions. Leaving out what the kit declared removes it;
what it never declared is never touched; rolling back plans an earlier version; removing plans nothing."""

import pytest
import yaml
from fastapi import BackgroundTasks

from src.agents.repository import AgentRepository
from src.apikeys.repository import ApiKeyRepository
from src.blueprints.approval import approval_form
from src.blueprints.catalog import example_yaml
from src.blueprints.kinds import knowledge_base as knowledge_base_kind
from src.blueprints.kinds.agent import UnlinkKnowledgeBase
from src.blueprints.kinds.knowledge_base import DeleteKnowledgeBase
from src.blueprints.kits import KitError, KitRepository, KitStatus, declared, plan_kit_removal, plan_rollback
from src.blueprints.models import DeploymentAction, DeploymentStatus
from src.blueprints.planner import plan_blueprint
from src.blueprints.service import Blocked, Deployed, Invalid, apply_kit_plan, deploy_blueprint
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
    monkeypatch.setattr(settings, "is_superuser_email", lambda email: True)
    monkeypatch.setattr(KnowledgeBaseService, "_delete_pinecone_namespace", lambda self, kb_id: 0)
    ProviderSettingsRepository().save(
        ProviderSettings(user_email=TEST_USER_EMAIL, provider_name="Bedrock", encrypted_credentials="{}")
    )


def deploy(text: str, kit_id: str | None = None, params: dict | None = None) -> Deployed:
    outcome = deploy_blueprint(text, PARAMS if params is None else params, TEST_USER_EMAIL, BackgroundTasks(), kit_id=kit_id)
    assert isinstance(outcome, Deployed), outcome
    return outcome


def edited(text: str, change) -> str:
    document = yaml.safe_load(text)
    change(document["resources"])
    return yaml.safe_dump(document, sort_keys=False)


def linked(agent_id: str) -> set[str]:
    return {link.kb_id for link in AgentKnowledgeBaseRepository().find_kbs_for_agent(agent_id)}


def plan_next(text: str, kit_id: str):
    kit = KitRepository().find(TEST_USER_EMAIL, kit_id)
    validated = validate_blueprint(text, PARAMS)
    return validated, plan_blueprint(validated, TEST_USER_EMAIL, declared(kit))


# --- A kit and its versions ----------------------------------------------------------------------


def test_the_first_build_is_a_kit_and_each_change_a_version():
    first = deploy(SITE_AGENT)
    kit = first.kit
    assert kit is not None and kit.title == "Website support agent"  # the blueprint's title
    assert (kit.current_version, kit.versions) == (1, 1)
    assert set(kit.resources) == {"site_kb", "assistant", "widget"}
    assert (first.deployment.kit_id, first.deployment.version) == (kit.kit_id, 1)

    # The same again changes nothing, so it isn't a version.
    again = deploy(SITE_AGENT, kit.kit_id)
    assert again.kit.versions == 1 and not again.plan.changes_anything

    changed = deploy(SITE_AGENT.replace("short and friendly", "short"), kit.kit_id)
    assert (changed.kit.current_version, changed.deployment.version) == (2, 2)
    # The kit, not the YAML, says which resource each name is.
    assert changed.kit.resources["assistant"].id == kit.resources["assistant"].id


def test_leaving_out_a_link_takes_it_away_but_never_what_the_kit_didnt_declare():
    kit = deploy(SITE_AGENT).kit
    agent_id, site_kb = kit.resources["assistant"].id, kit.resources["site_kb"].id
    docs = KnowledgeBaseRepository().save(KnowledgeBase(name="Docs", created_by=TEST_USER_EMAIL))
    AgentKnowledgeBaseRepository().link(agent_id, docs.kb_id, TEST_USER_EMAIL)  # from the dashboard

    without = edited(SITE_AGENT, lambda r: r["assistant"].update(knowledge_bases=[]))
    result = deploy(without, kit.kit_id)
    step = next(step for step in result.plan.steps if step.resource == "assistant")
    assert step.removals == ["disconnect knowledge base 'Acme website'"]
    assert linked(agent_id) == {docs.kb_id}  # the kit never declared Docs
    assert KnowledgeBaseRepository().find_by_id(site_kb, TEST_USER_EMAIL).status != KnowledgeBaseStatus.DELETED


def test_one_of_two_installs_of_a_skill_can_go():
    two = edited(SITE_AGENT, lambda r: r["assistant"]["skills"].extend([
        {"id": "send_email", "config": {"to": "sales@acme.example"}},
        {"id": "send_email", "config": {"to": "support@acme.example"}},
    ]))
    kit = deploy(two).kit
    one = edited(two, lambda r: r["assistant"]["skills"].pop())
    deploy(one, kit.kit_id)
    installs = AgentSkillRepository().list_by_agent(kit.resources["assistant"].id)
    assert sorted(i.config["to"] for i in installs if i.skill_id == "send_email") == ["sales@acme.example"]


def test_leaving_out_resources_deletes_them_dependents_first():
    kit = deploy(SITE_AGENT).kit
    agent_id = kit.resources["assistant"].id
    only_kb = edited(SITE_AGENT, lambda r: (r.pop("assistant"), r.pop("widget")))
    document = yaml.safe_load(only_kb)
    document["outputs"] = {}
    result = deploy(yaml.safe_dump(document, sort_keys=False), kit.kit_id)

    assert result.deployment.status == DeploymentStatus.APPLIED
    assert [line.split(":")[0] for line in result.deployment.removed] == [
        "delete chat widget 'Acme assistant widget'", "delete agent 'Acme assistant'",
    ]
    assert AgentRepository().find_agent_by_id(agent_id, TEST_USER_EMAIL) is None
    assert ApiKeyRepository().find_all_by_agent(agent_id) == []
    assert set(result.kit.resources) == {"site_kb"}


def test_a_knowledge_base_used_outside_the_kit_isnt_deleted_with_it():
    kit = deploy(SITE_AGENT).kit
    other = AgentRepository().find_agent_by_id(kit.resources["assistant"].id, TEST_USER_EMAIL).model_copy(
        update={"agent_id": "outsider", "agent_name": "Outsider"}
    )
    AgentRepository().save(other)
    AgentKnowledgeBaseRepository().link("outsider", kit.resources["site_kb"].id, TEST_USER_EMAIL)
    without_kb = edited(SITE_AGENT, lambda r: (r.pop("site_kb"), r["assistant"].update(knowledge_bases=[])))
    document = yaml.safe_load(without_kb)
    document["outputs"].pop("crawl_job_id", None)
    _, plan = plan_next(yaml.safe_dump(document, sort_keys=False), kit.kit_id)
    assert any("outside this kit" in issue.message for issue in plan.blockers)


def test_renaming_a_resource_carries_it_on():
    """A new name for the same agent (same name shown, or its id) is the same agent, never deleted and rebuilt."""
    kit = deploy(SITE_AGENT).kit
    agent_id = kit.resources["assistant"].id
    renamed = SITE_AGENT.replace("  assistant:\n", "  helper:\n").replace("agent: assistant", "agent: helper").replace(
        "resources.assistant.", "resources.helper."
    )
    result = deploy(renamed, kit.kit_id)
    assert result.deployment.removed == []
    assert result.kit.resources["helper"].id == agent_id and "assistant" not in result.kit.resources
    assert AgentRepository().find_agent_by_id(agent_id, TEST_USER_EMAIL) is not None


def test_a_rename_that_would_rebuild_a_resource_is_asked_about():
    """Knowledge bases aren't matched by a shared name, so a renamed one with no id would be deleted and rebuilt."""
    kit = deploy(SITE_AGENT).kit
    KnowledgeBaseRepository().save(KnowledgeBase(name="Acme website", created_by=TEST_USER_EMAIL))  # same name
    renamed = SITE_AGENT.replace("  site_kb:\n", "  pages:\n").replace("[site_kb]", "[pages]").replace(
        "resources.site_kb.", "resources.pages."
    )
    _, plan = plan_next(renamed, kit.kit_id)
    [issue] = [issue for issue in plan.blockers if issue.path == "resources.pages"]
    assert "looks like 'site_kb' renamed" in issue.message and kit.resources["site_kb"].id in issue.hint


def test_a_name_that_changes_kind_is_refused():
    kit = deploy(SITE_AGENT).kit
    document = yaml.safe_load(edited(SITE_AGENT, lambda r: r.update(widget={"kind": "KnowledgeBase", "name": "Other"})))
    document["outputs"].pop("snippet", None)
    _, plan = plan_next(yaml.safe_dump(document, sort_keys=False), kit.kit_id)
    assert any(issue.path == "resources.widget.kind" for issue in plan.blockers)


def test_drift_is_reported_and_left_alone():
    kit = deploy(SITE_AGENT).kit
    agent = AgentRepository().find_agent_by_id(kit.resources["assistant"].id, TEST_USER_EMAIL)
    AgentRepository().save(agent.model_copy(update={"agent_persona": "Edited in the dashboard."}))
    _, plan = plan_next(SITE_AGENT.replace("allow_guests: true", "allow_guests: false"), kit.kit_id)
    step = next(step for step in plan.steps if step.resource == "assistant")
    assert step.action == "unchanged" and step.drift == ["instructions was changed outside the blueprint; it stays as it is"]


# --- Rolling back and removing -------------------------------------------------------------------


def test_rolling_back_plans_the_earlier_version_and_applies_only_that_plan():
    kit = deploy(SITE_AGENT).kit
    agent_id = kit.resources["assistant"].id
    with_canvas = edited(SITE_AGENT, lambda r: r["assistant"]["skills"].append({"id": "html_canvas"}))
    kit = deploy(with_canvas.replace("short and friendly", "terse"), kit.kit_id).kit

    planned = plan_rollback(TEST_USER_EMAIL, kit.kit_id, 1)
    assert planned.plan.ok and "uninstall skill html canvas" in planned.plan.removals
    assert isinstance(apply_kit_plan(planned, TEST_USER_EMAIL, kit.kit_id, "not-that-plan"), Invalid)

    result = apply_kit_plan(planned, TEST_USER_EMAIL, kit.kit_id, planned.plan_id)
    assert isinstance(result, Deployed)
    assert (result.deployment.action, result.deployment.rolled_back_to, result.kit.current_version) == (
        DeploymentAction.ROLLBACK, 1, 3,
    )
    assert "short and friendly" in AgentRepository().find_agent_by_id(agent_id, TEST_USER_EMAIL).agent_persona
    assert {s.skill_id for s in AgentSkillRepository().list_by_agent(agent_id)} == {"lead_capture"}
    # The plan seen before that rollback is stale now: planned again, it has another id.
    again = plan_rollback(TEST_USER_EMAIL, kit.kit_id, 1)
    assert isinstance(apply_kit_plan(again, TEST_USER_EMAIL, kit.kit_id, planned.plan_id), Invalid)


def test_removing_a_kit_deletes_everything_it_holds():
    kit = deploy(SITE_AGENT).kit
    agent_id, kb_id = kit.resources["assistant"].id, kit.resources["site_kb"].id
    planned = plan_kit_removal(TEST_USER_EMAIL, kit.kit_id)
    assert {step.action for step in planned.plan.steps} == {"remove"}

    result = apply_kit_plan(planned, TEST_USER_EMAIL, kit.kit_id, planned.plan_id)
    assert isinstance(result, Deployed) and result.deployment.status == DeploymentStatus.APPLIED
    assert (result.kit.status, result.kit.resources) == (KitStatus.REMOVED, {})
    assert AgentRepository().find_agent_by_id(agent_id, TEST_USER_EMAIL) is None
    assert KnowledgeBaseRepository().find_by_id(kb_id, TEST_USER_EMAIL).status == KnowledgeBaseStatus.DELETED
    with pytest.raises(KitError, match="removed"):
        plan_kit_removal(TEST_USER_EMAIL, kit.kit_id)


# --- Failures --------------------------------------------------------------------------------------


def test_a_failed_disconnect_puts_everything_back(monkeypatch):
    """Disconnecting can be undone, so it runs before the commit point, and a failure undoes the whole apply."""
    kit = deploy(SITE_AGENT).kit
    agent_id = kit.resources["assistant"].id
    monkeypatch.setattr(UnlinkKnowledgeBase, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("links down")))
    without = edited(SITE_AGENT.replace("short and friendly", "terse"), lambda r: r["assistant"].update(knowledge_bases=[]))
    result = deploy(without, kit.kit_id)
    assert result.deployment.status == DeploymentStatus.FAILED and result.deployment.removed == []
    assert "short and friendly" in AgentRepository().find_agent_by_id(agent_id, TEST_USER_EMAIL).agent_persona
    assert result.kit.versions == 1  # a failure put back isn't a version


def test_a_failed_delete_keeps_the_rest_and_says_so(monkeypatch):
    """Deleting can't be undone, so it runs after the commit point; a failure there leaves the rest applied."""
    kit = deploy(SITE_AGENT).kit
    monkeypatch.setattr(DeleteKnowledgeBase, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("vectors down")))
    document = yaml.safe_load(edited(SITE_AGENT.replace("short and friendly", "terse"), lambda r: (
        r.pop("site_kb"), r["assistant"].update(knowledge_bases=[]),
    )))
    document["outputs"].pop("crawl_job_id", None)
    result = deploy(yaml.safe_dump(document, sort_keys=False), kit.kit_id)
    assert result.deployment.status == DeploymentStatus.FAILED_PARTIAL
    assert "didn't finish: vectors down" in result.deployment.error
    # A version, but the kit still declares the last full one, so applying again retries the delete.
    assert (result.kit.versions, result.kit.current_version) == (2, 1)
    assert "site_kb" in result.kit.resources


def test_the_approval_and_the_drawing_call_out_removals():
    kit = deploy(SITE_AGENT).kit
    document = yaml.safe_load(SITE_AGENT)
    document["resources"].pop("widget")
    document["outputs"].pop("snippet", None)
    validated, plan = plan_next(yaml.safe_dump(document, sort_keys=False), kit.kit_id)
    help_text = approval_form("p1", plan, {})["form"]["form_inputs"][0]["attr"]["help_text"]
    assert "This removes, and it can't be undone:\n- delete chat widget" in help_text
    html = render_drawing(drawing_for(validated, plan, stage="plan", plan_id="p1"))
    assert "Acme assistant widget" in html and '<ul class="removals">' in html


def test_a_kit_that_isnt_the_persons_cant_be_deployed_to():
    assert isinstance(deploy_blueprint(SITE_AGENT, PARAMS, TEST_USER_EMAIL, kit_id="nope"), Invalid)
    blocked = deploy_blueprint(SITE_AGENT, {**PARAMS, "provider": "OpenAI"}, TEST_USER_EMAIL)
    assert isinstance(blocked, Blocked)


# --- v1 documents ----------------------------------------------------------------------------------


def test_a_v1_document_is_read_as_what_it_keeps():
    v1 = SITE_AGENT.replace("apiVersion: innomight/v2", "apiVersion: innomight/v1").replace(
        "  widget:\n    kind: WidgetKey\n", "  widget:\n    kind: WidgetKey\n    remove: true\n    id: key-1\n"
    ).replace("    knowledge_bases: [site_kb]\n", "    knowledge_bases: [site_kb]\n    remove_skills: [html_canvas]\n")
    document = yaml.safe_load(v1)
    document["outputs"].pop("snippet", None)
    validated = validate_blueprint(yaml.safe_dump(document, sort_keys=False), PARAMS)
    assert set(validated.blueprint.resources) == {"site_kb", "assistant"}


# --- Over HTTP ---------------------------------------------------------------------------------------


def test_the_kits_api(test_client, auth_headers):
    built = test_client.post("/blueprints/deployments", headers=auth_headers, json={"yaml": SITE_AGENT, "params": PARAMS})
    assert built.status_code == 201, built.text
    kit_id = built.json()["kit_id"]
    changed = test_client.post("/blueprints/deployments", headers=auth_headers, json={
        "yaml": SITE_AGENT.replace("short and friendly", "terse"), "params": PARAMS, "kit_id": kit_id,
    })
    assert changed.status_code == 201, changed.text

    [summary] = test_client.get("/kits", headers=auth_headers).json()
    assert (summary["kit_id"], summary["versions"], summary["counts"]) == (
        kit_id, 2, {"KnowledgeBase": 1, "Agent": 1, "WidgetKey": 1},
    )
    detail = test_client.get(f"/kits/{kit_id}", headers=auth_headers).json()
    assert [v["version"] for v in detail["history"]] == [2, 1] and detail["history"][0]["current"]
    agent = next(r for r in detail["resources"] if r["kind"] == "Agent")
    assert agent["title"] == "Acme assistant" and agent["dashboard_path"].startswith("/dashboard/agents/")

    planned = test_client.post(f"/kits/{kit_id}/rollback/plan", headers=auth_headers, json={"version": 1}).json()
    assert planned["ok"] and planned["plan_id"]
    stale = test_client.post(f"/kits/{kit_id}/rollback", headers=auth_headers, json={"version": 1, "plan_id": "x"})
    assert stale.status_code == 409
    rolled = test_client.post(
        f"/kits/{kit_id}/rollback", headers=auth_headers, json={"version": 1, "plan_id": planned["plan_id"]}
    )
    assert rolled.status_code == 200 and rolled.json()["rolled_back_to"] == 1

    removal = test_client.post(f"/kits/{kit_id}/removal/plan", headers=auth_headers).json()
    removed = test_client.post(f"/kits/{kit_id}/remove", headers=auth_headers, json={"plan_id": removal["plan_id"]})
    assert removed.status_code == 200, removed.text
    assert test_client.get(f"/kits/{kit_id}", headers=auth_headers).json()["status"] == "removed"
    assert test_client.get("/kits/nope", headers=auth_headers).status_code == 404
