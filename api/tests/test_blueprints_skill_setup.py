"""Skills by what they need before they work, and the "needs settings" tier built end to end: settings that name
another agent, and skills installed more than once."""

import pytest
import yaml
from fastapi import BackgroundTasks

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.blueprints.book import SKILL_CHAPTERS, blueprint_book
from src.blueprints.catalog import example_yaml
from src.blueprints.executor import apply_blueprint
from src.blueprints.export import export_agent
from src.blueprints.issues import BlueprintInvalid
from src.blueprints.kinds import knowledge_base as knowledge_base_kind
from src.blueprints.models import DeploymentStatus
from src.blueprints.planner import plan_blueprint
from src.blueprints.skills_schema import SkillSetup, skill_variants
from src.blueprints.validator import validate_blueprint
from src.builder.canvas import drawing_for
from src.config import settings
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from src.skills.repository import AgentSkillRepository
from tests.mock_data import TEST_USER_EMAIL

TEAM = example_yaml("agent-team") or ""
SITE_AGENT = example_yaml("site-agent") or ""
SITE_PARAMS = {"site_url": "https://acme.example", "business_name": "Acme"}


@pytest.fixture
def account(monkeypatch, dynamodb_table) -> None:
    monkeypatch.setattr(knowledge_base_kind, "launch_crawl", lambda job_id, *_: None)
    monkeypatch.setattr(settings, "require_pinecone", lambda: None)
    # Superuser: the free tier allows one agent, and these build two.
    monkeypatch.setattr(settings, "is_superuser_email", lambda email: True)
    ProviderSettingsRepository().save(
        ProviderSettings(user_email=TEST_USER_EMAIL, provider_name="Bedrock", encrypted_credentials="{}")
    )


def plan_for(text: str, params: dict | None = None):
    validated = validate_blueprint(text, params or {})
    return validated, plan_blueprint(validated, TEST_USER_EMAIL)


def build(text: str, params: dict | None = None):
    validated, plan = plan_for(text, params)
    assert plan.ok, plan.blockers
    return plan, apply_blueprint(validated, plan, TEST_USER_EMAIL, BackgroundTasks())


# --- Tiers -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "skill_id, setup",
    [
        ("html_canvas", SkillSetup.READY),
        ("rest_template", SkillSetup.READY),  # its only secret is optional
        ("send_email", SkillSetup.SETTINGS),
        ("agent_invocation", SkillSetup.READY),  # its settings are the build's design, which Ada writes
        ("wordpress_search", SkillSetup.SETTINGS),
        ("google_mail", SkillSetup.ACCOUNT),
        ("google_ads", SkillSetup.ACCOUNT),
        ("aws_cli", SkillSetup.SECRETS),  # the hardest need decides, though it also has settings
        ("league_insights_report", SkillSetup.SECRETS),
    ],
)
def test_a_skill_is_in_the_tier_its_manifest_implies(skill_id, setup):
    assert skill_variants()[skill_id].setup == setup


def test_every_skill_is_in_one_chapter_easiest_first():
    book = blueprint_book()
    titles = [chapter.title for chapter in book.chapters]
    assert [title for title in titles if title.startswith("Skills")] == [SKILL_CHAPTERS[s][0] for s in SkillSetup]
    pages = [page.id for chapter in book.chapters if chapter.title.startswith("Skills") for page in chapter.pages]
    assert sorted(pages) == sorted(f"skill/{skill_id}" for skill_id in skill_variants())


def test_a_page_says_which_settings_ada_writes_and_which_the_person_gives():
    invoke = blueprint_book().get("skill/agent_invocation").body
    assert "You write: `target_agent_id` (Agent), `usage_description`" in invoke
    assert "The person gives" not in invoke
    assert "target_agent_id: <an Agent's name in this blueprint>" in invoke.split("### Example")[1]

    email = blueprint_book().get("skill/send_email").body
    assert "The person gives: Recipient emails" in email and "You write" not in email
    assert "config:" not in email.split("### Example")[1]


# --- A setting that names another agent --------------------------------------------------------


def test_a_team_installs_the_lead_pointing_at_the_new_specialist(account):
    plan, built = build(TEAM)
    assert [step.resource for step in plan.steps] == ["specialist", "lead"]
    assert built.status == DeploymentStatus.APPLIED
    specialist, lead = built.resources["specialist"].id, built.resources["lead"].id
    [install] = AgentSkillRepository().list_by_agent(lead)
    assert install.config["target_agent_id"] == specialist

    # Applying it again changes nothing: the name resolves to the same id.
    again, _ = build(TEAM)
    assert not again.changes_anything


def test_the_drawing_wires_the_lead_to_its_specialist(account):
    validated, plan = plan_for(TEAM)
    drawing = drawing_for(validated, plan, stage="plan", plan_id="p")
    assert drawing.edges == [("lead", "specialist", "hands work to")]
    assert {card.name: card.depth for card in drawing.cards} == {"lead": 0, "specialist": 1}  # the lead reads first


def test_an_exported_lead_plans_as_unchanged(account):
    _, built = build(TEAM)
    exported = export_agent(built.resources["lead"].id, TEST_USER_EMAIL)
    _, plan = plan_for(exported or "")
    assert plan.ok and not plan.changes_anything


def test_an_agent_id_works_if_it_is_yours(account):
    mine = AgentRepository().save(Agent(
        agent_name="Researcher", agent_architecture="krishna-memgpt", agent_provider="Bedrock",
        agent_persona="Research things.", created_by=TEST_USER_EMAIL,
    ))
    text = TEAM.replace("target_agent_id: specialist", f"target_agent_id: {mine.agent_id}")
    _, plan = plan_for(text)
    assert plan.ok, plan.blockers

    _, plan = plan_for(TEAM.replace("target_agent_id: specialist", "target_agent_id: someone-elses-agent"))
    assert [issue.path for issue in plan.blockers] == ["resources.lead.skills[0]"]


@pytest.mark.parametrize(
    "target, message",
    [
        ("lead", "can't name the agent itself"),
        ("knowledge", "is a KnowledgeBase, not an Agent"),
    ],
)
def test_a_setting_must_name_another_agent(target, message):
    document = yaml.safe_load(TEAM)
    document["resources"]["knowledge"] = {"kind": "KnowledgeBase", "name": "Notes"}
    document["resources"]["lead"]["skills"][0]["config"]["target_agent_id"] = target
    with pytest.raises(BlueprintInvalid) as raised:
        validate_blueprint(yaml.safe_dump(document, sort_keys=False), {})
    assert any(message in issue.message for issue in raised.value.issues)


def test_a_removed_agent_cant_be_named():
    document = yaml.safe_load(TEAM)
    document["resources"]["specialist"].update({"id": "agent-1", "remove": True})
    with pytest.raises(BlueprintInvalid) as raised:
        validate_blueprint(yaml.safe_dump(document, sort_keys=False), {})
    assert "resources.lead.skills[0].config.target_agent_id" in {issue.path for issue in raised.value.issues}


# --- A skill installed more than once ----------------------------------------------------------


def test_each_send_email_entry_is_its_own_install(account):
    document = yaml.safe_load(SITE_AGENT)
    document["resources"]["assistant"]["skills"] += [
        {"id": "send_email", "config": {"to": "sales@acme.example"}},
        {"id": "send_email", "config": {"to": "support@acme.example"}},
    ]
    text = yaml.safe_dump(document, sort_keys=False)
    _, built = build(text, SITE_PARAMS)
    installs = AgentSkillRepository().list_by_agent(built.resources["assistant"].id)
    assert sorted(i.config["to"] for i in installs if i.skill_id == "send_email") == [
        "sales@acme.example", "support@acme.example",
    ]

    again, _ = build(text, SITE_PARAMS)
    assert not again.changes_anything

    # A third recipient list is one more install; the two already there are kept as they are.
    document["resources"]["assistant"]["skills"].append({"id": "send_email", "config": {"to": "ops@acme.example"}})
    plan, built = build(yaml.safe_dump(document, sort_keys=False), SITE_PARAMS)
    [assistant] = [step for step in plan.steps if step.resource == "assistant"]
    assert assistant.changes == ["add skill send email"]
    installs = AgentSkillRepository().list_by_agent(built.resources["assistant"].id)
    assert len([i for i in installs if i.skill_id == "send_email"]) == 3
