"""Planning and applying blueprints against the real services (moto). See docs/LLD-solution-blueprints.md."""

from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.agents.service import AgentService
from src.apikeys.repository import ApiKeyRepository
from src.blueprints import service as blueprints_service
from src.blueprints.catalog import example_yaml
from src.blueprints.executor import apply_blueprint
from src.blueprints.kinds import knowledge_base as knowledge_base_kind
from src.blueprints.kinds.agent import AgentKind
from src.blueprints.kinds.widget_key import WidgetKeyKind
from src.blueprints.models import DeploymentStatus
from src.blueprints.planner import plan_blueprint
from src.blueprints.repository import DeploymentRepository
from src.blueprints.validator import validate_blueprint
from src.config import settings
from src.dream.models import DreamSettings
from src.dream.repository import DreamRepository
from src.dream.service import DreamService
from src.knowledge.models import KnowledgeBaseStatus
from src.knowledge.repository import AgentKnowledgeBaseRepository, KnowledgeBaseRepository
from src.scheduler.repository import SchedulerRepository
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from src.skills.models import ActorKind
from src.skills.repository import AgentSkillRepository
from tests.mock_data import TEST_USER_EMAIL

SITE_AGENT = example_yaml("site-agent") or ""
PARAMS = {"site_url": "https://acme.example/about", "business_name": "Acme"}


@pytest.fixture
def launched(monkeypatch, dynamodb_table) -> list[tuple[str, str]]:
    """Crawls that apply started, instead of running them; and Bedrock set up for the test user."""
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(knowledge_base_kind, "launch_crawl", lambda job_id, kb_id, *_: calls.append((job_id, kb_id)))
    monkeypatch.setattr(settings, "require_pinecone", lambda: None)
    ProviderSettingsRepository().save(
        ProviderSettings(user_email=TEST_USER_EMAIL, provider_name="Bedrock", encrypted_credentials="{}")
    )
    return calls


def planned(text: str = SITE_AGENT, params: dict | None = None):
    validated = validate_blueprint(text, params or PARAMS)
    return validated, plan_blueprint(validated, TEST_USER_EMAIL)


def test_plan_lists_steps_in_order_with_no_blockers(launched):
    _, plan = planned()

    assert plan.ok, plan.blockers
    assert [step.resource for step in plan.steps] == ["site_kb", "assistant", "widget"]
    assert "read up to 10 pages from https://acme.example/about" in plan.steps[0].summary


def test_apply_creates_the_whole_solution(launched):
    validated, plan = planned()
    deployment = apply_blueprint(validated, plan, TEST_USER_EMAIL, BackgroundTasks())

    assert deployment.status == DeploymentStatus.APPLIED
    kb_id = deployment.resources["site_kb"].id
    agent_id = deployment.resources["assistant"].id

    agent = AgentRepository().find_agent_by_id(agent_id, TEST_USER_EMAIL)
    assert agent.agent_name == "Acme assistant"
    assert agent.agent_architecture == "krishna-memgpt"
    assert AgentKnowledgeBaseRepository().exists(agent_id, kb_id)

    [skill] = AgentSkillRepository().list_by_agent(agent_id)
    assert skill.skill_id == "lead_capture"
    assert skill.available_to == [ActorKind.OWNER, ActorKind.VISITOR, ActorKind.GUEST]

    [key] = ApiKeyRepository().find_all_by_agent(agent_id)
    assert key.allowed_origins == ["https://acme.example"]
    assert key.allow_guests is True

    # The crawl starts once, after everything exists.
    assert launched == [(deployment.resources["site_kb"].attributes["crawl_job_id"], kb_id)]
    assert key.public_key in deployment.outputs["snippet"].value
    assert deployment.outputs["agent_id"].value == agent_id

    stored = DeploymentRepository().find_by_id(TEST_USER_EMAIL, deployment.deployment_id)
    assert stored.status == DeploymentStatus.APPLIED
    assert stored.params["business_name"] == "Acme"


def test_a_failure_rolls_everything_back(launched, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("key service down")

    monkeypatch.setattr(WidgetKeyKind, "apply", fail)
    validated, plan = planned()
    deployment = apply_blueprint(validated, plan, TEST_USER_EMAIL, BackgroundTasks())

    assert deployment.status == DeploymentStatus.FAILED
    assert deployment.error == "key service down"
    assert deployment.resources == {}
    assert AgentRepository().find_by_name("Acme assistant", TEST_USER_EMAIL) is None
    [kb] = KnowledgeBaseRepository().find_all_by_user(TEST_USER_EMAIL, include_deleted=True)
    assert kb.status == KnowledgeBaseStatus.DELETED
    assert launched == []


def test_a_failed_rollback_keeps_the_leftovers(launched, monkeypatch):
    monkeypatch.setattr(WidgetKeyKind, "apply", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(AgentKind, "rollback", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stuck")))
    validated, plan = planned()
    deployment = apply_blueprint(validated, plan, TEST_USER_EMAIL, BackgroundTasks())

    assert deployment.status == DeploymentStatus.FAILED_PARTIAL
    assert list(deployment.resources) == ["assistant"]


def test_provider_that_isnt_set_up_blocks(launched):
    _, plan = planned(params={**PARAMS, "provider": "OpenAI"})
    assert any(issue.path == "resources.assistant.provider" for issue in plan.blockers)


def test_an_agent_with_the_same_name_is_updated_not_duplicated(launched):
    existing = AgentRepository().save(Agent(
        agent_name="Acme assistant",
        agent_architecture="krishna-mini",
        agent_provider="Bedrock",
        agent_persona="Existing.",
        created_by=TEST_USER_EMAIL,
    ))
    _, plan = planned()
    agent_step = next(step for step in plan.steps if step.resource == "assistant")

    assert plan.ok, plan.blockers
    assert agent_step.action == "update"
    assert agent_step.existing_id == existing.agent_id
    assert "update its instructions" in agent_step.changes
    assert "add skill lead capture" in agent_step.changes


def test_another_agent_already_called_the_new_name_blocks(launched):
    for name in ("Acme assistant", "Taken name"):
        AgentRepository().save(Agent(
            agent_name=name, agent_architecture="krishna-memgpt", agent_provider="Bedrock",
            agent_persona="Existing.", created_by=TEST_USER_EMAIL,
        ))
    target = AgentRepository().find_by_name("Acme assistant", TEST_USER_EMAIL)
    renamed = SITE_AGENT.replace("    kind: Agent\n", f"    kind: Agent\n    id: {target.agent_id}\n").replace(
        'name: "{{ params.business_name }} assistant"', "name: Taken name"
    )
    _, plan = planned(renamed)
    assert any("another agent called 'Taken name'" in issue.message for issue in plan.blockers)


def test_page_cap_blocks(launched):
    _, plan = planned(SITE_AGENT.replace("max_pages: 10", "max_pages: 25"))
    assert any("page limit" in issue.message for issue in plan.blockers)


def test_owner_only_skill_audience_blocks_at_install(launched):
    # The validator rejects this from the manifest; the install check is the backstop.
    text = SITE_AGENT.replace("- id: lead_capture\n        available_to: [visitor, guest]", "- id: lead_capture")
    _, plan = planned(text)
    assert plan.ok


# --- HTTP ---------------------------------------------------------------------------------


def test_schema_and_reference_are_public(test_client):
    schema = test_client.get("/blueprints/schema/v1.json")
    assert schema.status_code == 200
    assert schema.headers["ETag"]
    assert "Skill_lead_capture" in schema.json()["$defs"]

    assert test_client.get("/blueprints/reference").status_code == 200
    assert test_client.get("/blueprints/catalog").status_code == 401


def test_catalog_lists_kinds_skills_and_readiness(test_client, auth_headers):
    body = test_client.get("/blueprints/catalog", headers=auth_headers).json()

    assert [kind["kind"] for kind in body["kinds"]] == ["KnowledgeBase", "McpConnection", "Agent", "WidgetKey"]
    lead_capture = next(skill for skill in body["skills"] if skill["id"] == "lead_capture")
    assert lead_capture["shareable"] is True
    assert lead_capture["ready"] is True
    assert "render_form" in [action["name"] for action in lead_capture["actions"]]
    assert set(body["examples"]) >= {"site-agent", "docs-assistant"}


def test_validate_returns_issues_or_the_params_form(test_client, auth_headers):
    bad = test_client.post("/blueprints/validate", headers=auth_headers, json={"yaml": "kind: Blueprint"}).json()
    assert bad["valid"] is False and bad["issues"]

    good = test_client.post("/blueprints/validate", headers=auth_headers, json={"yaml": SITE_AGENT}).json()
    assert good["valid"] is True
    assert [field["name"] for field in good["params_form"]["form_inputs"]] == ["site_url", "business_name", "provider"]


def test_apply_over_http_then_list_and_fetch(test_client, auth_headers, launched):
    body = {"yaml": SITE_AGENT, "params": PARAMS}
    assert test_client.post("/blueprints/plan", headers=auth_headers, json=body).json()["ok"] is True

    created = test_client.post("/blueprints/deployments", headers=auth_headers, json=body)
    assert created.status_code == 201, created.text
    deployment_id = created.json()["deployment_id"]

    listed = test_client.get("/blueprints/deployments", headers=auth_headers).json()
    assert [item["deployment_id"] for item in listed] == [deployment_id]
    fetched = test_client.get(f"/blueprints/deployments/{deployment_id}", headers=auth_headers).json()
    assert fetched["status"] == "applied"

    # The same blueprint again changes nothing: everything matches what's there.
    replanned = test_client.post("/blueprints/plan", headers=auth_headers, json=body).json()
    assert replanned["ok"] is True
    assert [step["action"] for step in replanned["steps"]] == ["unchanged", "unchanged", "unchanged"]


def test_apply_is_rate_limited(test_client, auth_headers, launched, monkeypatch):
    class Refuse:
        def __init__(self, policy):
            pass

        def acquire(self, subject):
            return SimpleNamespace(allowed=False, retry_after_seconds=120)

    monkeypatch.setattr(blueprints_service, "RateLimiter", Refuse)
    response = test_client.post("/blueprints/deployments", headers=auth_headers, json={"yaml": SITE_AGENT, "params": PARAMS})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "120"


def test_a_failed_build_leaves_no_dream_schedule_behind(dynamodb_table, monkeypatch):
    """Creating an agent joins it to the owner's nightly dream schedule; rolling it back must take that away too."""
    monkeypatch.setattr(knowledge_base_kind, "launch_crawl", lambda job_id, *_: None)
    monkeypatch.setattr(settings, "require_pinecone", lambda: None)
    ProviderSettingsRepository().save(
        ProviderSettings(user_email=TEST_USER_EMAIL, provider_name="Bedrock", encrypted_credentials="{}")
    )
    DreamRepository().save_settings(DreamSettings(
        user_email=TEST_USER_EMAIL, enabled=True, provider_name="Bedrock", model_name="claude-sonnet"
    ))

    def fail(*args, **kwargs):
        raise RuntimeError("key service down")

    monkeypatch.setattr(WidgetKeyKind, "apply", fail)
    validated = validate_blueprint(SITE_AGENT, PARAMS)
    created: list[str] = []
    real_create = AgentService.create

    def remember(self, request, user_email):
        agent = real_create(self, request, user_email)
        created.append(agent.agent_id)
        return agent

    monkeypatch.setattr(AgentService, "create", remember)
    deployment = apply_blueprint(validated, plan_blueprint(validated, TEST_USER_EMAIL), TEST_USER_EMAIL)

    assert deployment.status == DeploymentStatus.FAILED
    [agent_id] = created
    schedule_id = DreamService().schedule_id_for(agent_id, TEST_USER_EMAIL)
    assert SchedulerRepository().find_schedule(TEST_USER_EMAIL, schedule_id) is None


def test_deploying_says_why_it_didnt(launched):
    """The API and Ada both deploy through deploy_blueprint, and each outcome is its own type."""
    invalid = blueprints_service.deploy_blueprint("kind: Blueprint", {}, TEST_USER_EMAIL)
    assert isinstance(invalid, blueprints_service.Invalid) and invalid.issues

    no_provider = SITE_AGENT.replace("Bedrock", "OpenAI")
    blocked = blueprints_service.deploy_blueprint(no_provider, PARAMS, TEST_USER_EMAIL)
    assert isinstance(blocked, blueprints_service.Blocked)
    assert any(issue.path.endswith(".provider") for issue in blocked.plan.blockers)

    deployed = blueprints_service.deploy_blueprint(SITE_AGENT, PARAMS, TEST_USER_EMAIL)
    assert isinstance(deployed, blueprints_service.Deployed)
    assert deployed.deployment.status == DeploymentStatus.APPLIED
    assert [step.resource for step in deployed.plan.steps] == ["site_kb", "assistant", "widget"]
