"""Ila, the solution builder: the Vishwakarma architecture, her tools and her routes."""

import json

import boto3
import pytest
import yaml

from src.agents.agentic_loop import PromptRefreshNeeded, TurnComplete
from src.agents.architectures import get_agent_architecture
from src.agents.architectures import vishwakarma
from src.agents.repository import AgentRepository
from src.agents.runtime_state import AgentTurnState
from src.blueprints.approval import APPROVE, REVISE, approval_label
from src.blueprints.catalog import example_yaml
from src.blueprints.executor import apply_blueprint
from src.blueprints.kinds import knowledge_base as knowledge_base_kind
from src.blueprints.planner import plan_blueprint
from src.blueprints.validator import validate_blueprint
from src.builder import router as builder_router
from src.builder.ila import ILA_AGENT_ID, GREETING, ila_agent
from src.builder.canvas import drawing_for, highlight_yaml, render_drawing
from src.builder.models import BuilderSession
from src.builder.repository import BuilderSessionRepository
from src.builder.tools import BuilderTools, build_builder_tool_registry, builder_tool_definitions
from src.config import settings
from src.conversations.models import Conversation
from src.conversations.repository import ConversationRepository
from src.llm.events import SSEEvent, SSEEventType
from src.messages.models import Message
from src.messages.repositories import get_message_repository
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from src.skills.models import ActorKind
from src.skills.registry import get_skill_registry
from tests.mock_data import TEST_USER_EMAIL

SITE_AGENT = example_yaml("site-agent") or ""
PARAMS = {"site_url": "https://acme.example", "business_name": "Acme"}


@pytest.fixture
def account(monkeypatch, dynamodb_table) -> list[str]:
    """Bedrock set up for the user, crawls recorded instead of run."""
    launched: list[str] = []
    monkeypatch.setattr(knowledge_base_kind, "launch_crawl", lambda job_id, *_: launched.append(job_id))
    monkeypatch.setattr(settings, "require_pinecone", lambda: None)
    ProviderSettingsRepository().save(
        ProviderSettings(user_email=TEST_USER_EMAIL, provider_name="Bedrock", encrypted_credentials="{}")
    )
    return launched


@pytest.fixture
def session(account) -> BuilderSession:
    conversation = ConversationRepository().save(
        Conversation(title="Building with Ila", agent_id=ILA_AGENT_ID, created_by=TEST_USER_EMAIL)
    )
    return BuilderSessionRepository().save(
        BuilderSession(conversation_id=conversation.conversation_id, user_email=TEST_USER_EMAIL, provider="Bedrock")
    )


def turn_state(session: BuilderSession) -> AgentTurnState:
    return AgentTurnState(
        owner_email=TEST_USER_EMAIL,
        actor_email=TEST_USER_EMAIL,
        actor_id=TEST_USER_EMAIL,
        actor_kind=ActorKind.OWNER,
        conversation_id=session.conversation_id,
        agent_id=ILA_AGENT_ID,
        model_name="",
        user_message="",
    )


def say(session: BuilderSession, role: str, content: str) -> None:
    get_message_repository().save(
        Message(conversation_id=session.conversation_id, role=role, content=content, created_by=TEST_USER_EMAIL)
    )


def approval(plan_id: str, decision: str = APPROVE) -> str:
    return f'<form_submission label="{approval_label(plan_id)}">\n- Decision: {decision}\n</form_submission>'


# --- Not a selectable architecture ------------------------------------------------------------


def test_vishwakarma_is_not_in_the_agent_factory():
    with pytest.raises(ValueError):
        get_agent_architecture("vishwakarma")


def test_show_form_uses_the_interactive_forms_schema():
    show_form = next(tool for tool in builder_tool_definitions() if tool["name"] == "show_form")
    lead_capture = get_skill_registry().get("lead_capture").manifest.find_action("render_custom_form")
    assert show_form["name"] == "show_form"
    assert show_form["parameters"] == lead_capture.input_schema


# --- Tools ------------------------------------------------------------------------------------


async def test_show_form_renders_through_the_forms_module(session):
    result = json.loads(await BuilderTools().show_form("show_form", {
        "form_label": "What would you like to build?",
        "form_inputs": [{"input_type": "choice", "name": "idea", "label": "Idea",
                         "values": ["Website support agent", "Something else"], "attr": {"variant": "radio"}}],
    }, turn_state(session)))

    assert result["type"] == "ui_form_render"
    assert result["form"]["form_inputs"][0]["values"] == ["Website support agent", "Something else"]


async def test_plan_keeps_the_draft_and_shows_an_approval_form(session):
    result = json.loads(await BuilderTools().plan("plan_blueprint", {"yaml": SITE_AGENT, "params": PARAMS}, turn_state(session)))

    assert result["ok"] is True
    assert result["type"] == "ui_form_render"
    assert result["form"]["form_name"] == approval_label(result["plan_id"])
    stored = BuilderSessionRepository().find(TEST_USER_EMAIL, session.conversation_id)
    assert stored.draft_yaml == SITE_AGENT
    assert stored.draft_params == PARAMS
    assert stored.plan_id == result["plan_id"]


async def test_plan_with_issues_keeps_the_draft_but_no_plan(session):
    broken = SITE_AGENT.replace("    skills:", "    skils:")
    result = json.loads(await BuilderTools().plan("plan_blueprint", {"yaml": broken, "params": PARAMS}, turn_state(session)))

    assert result["ok"] is False
    assert result["issues"][0]["hint"] == "Did you mean 'skills'?"
    stored = BuilderSessionRepository().find(TEST_USER_EMAIL, session.conversation_id)
    assert stored.draft_yaml == broken and stored.plan_id is None


async def test_apply_needs_the_person_to_approve_the_current_plan(session):
    tools, state = BuilderTools(), turn_state(session)
    plan_id = json.loads(await tools.plan("plan_blueprint", {"yaml": SITE_AGENT, "params": PARAMS}, state))["plan_id"]

    say(session, "user", "yes do it")
    assert json.loads(await tools.apply("apply_blueprint", {"plan_id": plan_id}, state))["applied"] is False
    say(session, "user", approval(plan_id, REVISE))
    assert json.loads(await tools.apply("apply_blueprint", {"plan_id": plan_id}, state))["applied"] is False
    say(session, "user", approval(plan_id))
    assert json.loads(await tools.apply("apply_blueprint", {"plan_id": "other"}, state))["applied"] is False
    assert AgentRepository().find_by_name("Acme assistant", TEST_USER_EMAIL) is None


async def test_approved_plan_is_built_and_its_status_reported(session, account):
    tools, state = BuilderTools(), turn_state(session)
    plan_id = json.loads(await tools.plan("plan_blueprint", {"yaml": SITE_AGENT, "params": PARAMS}, state))["plan_id"]
    say(session, "user", approval(plan_id))

    built = json.loads(await tools.apply("apply_blueprint", {"plan_id": plan_id}, state))

    assert built["applied"] is True, built
    assert "pk_live_" in built["outputs"]["snippet"]["value"]
    agent_id = built["resources"]["assistant"]["id"]
    assert AgentRepository().find_agent_by_id(agent_id, TEST_USER_EMAIL).agent_name == "Acme assistant"
    stored = BuilderSessionRepository().find(TEST_USER_EMAIL, session.conversation_id)
    assert stored.deployment_id and stored.plan_id is None
    assert len(account) == 1

    status = json.loads(await tools.build_status("get_build_status", {}, state))
    assert status["built"] is True
    assert status["crawls"] == [{"knowledge_base": "site_kb", "status": "pending", "pages_read": 0, "pages_found": 0}]
    assert status["resources"]["assistant"]["dashboard_url"].endswith(f"/dashboard/agents/{agent_id}")


# --- Architecture -----------------------------------------------------------------------------


async def test_a_turn_runs_ila_with_only_her_tools(session, monkeypatch):
    seen: dict = {}

    async def fake_loop(**kwargs):
        seen["tools"] = [tool["name"] for tool in kwargs["tools"]]
        seen["first_prompt"] = kwargs["context"][0]["content"]
        # The model plans the blueprint; run the real tool through the real router.
        outcome = await kwargs["tool_router"].execute(
            tool_name="plan_blueprint",
            tool_input={"yaml": SITE_AGENT, "params": PARAMS},
            tool_use_id="t1",
            state=kwargs["state"],
        )
        yield SSEEvent(event_type=SSEEventType.TOOL_CALL_START, content="", tool_call_id="t1",
                       tool_name="plan_blueprint", tool_args={})
        yield SSEEvent(event_type=SSEEventType.TOOL_CALL_RESULT, content=outcome.result, tool_call_id="t1",
                       tool_name="plan_blueprint", success=outcome.success)
        assert outcome.refresh_prompt
        yield PromptRefreshNeeded()
        seen["refreshed_prompt"] = kwargs["context"][0]["content"]
        yield SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content="Here's the plan.")
        yield TurnComplete(full_text="Here's the plan.")

    async def fake_provider_session(agent, **kwargs):
        return type("Session", (), {"provider": object(), "credentials": {}})()

    monkeypatch.setattr(vishwakarma, "run_agentic_tool_loop", fake_loop)
    monkeypatch.setattr(vishwakarma, "open_provider_session", fake_provider_session)
    conversation = ConversationRepository().find_by_id(session.conversation_id, TEST_USER_EMAIL)

    events = [event async for event in vishwakarma.VishwakarmaArchitecture().handle_message(
        agent=ila_agent(session),
        conversation=conversation,
        user_message="A website support agent please",
        owner_email=TEST_USER_EMAIL,
        actor_email=TEST_USER_EMAIL,
        actor_id=TEST_USER_EMAIL,
        actor_kind=ActorKind.OWNER,
    )]

    assert seen["tools"] == [
        "open_pages", "search_book", "show_form", "plan_blueprint", "apply_blueprint", "list_my_agents", "load_agent", "get_build_status",
    ]
    assert "You are Ila" in seen["first_prompt"]
    # The book's index, not its pages: the recipe is listed, its YAML isn't there until it's opened.
    assert "`recipe/site-agent`: Website support agent." in seen["first_prompt"]
    assert "kind: WidgetKey" not in seen["first_prompt"]
    assert "No pages open." in seen["first_prompt"]
    assert "No draft yet." in seen["first_prompt"]
    assert "waiting for the person's approval" in seen["refreshed_prompt"]

    types = [event.event_type for event in events]
    assert SSEEventType.UI_FORM_RENDER in types  # the approval form reaches the chat
    assert types[-1] == SSEEventType.STREAM_COMPLETE
    saved = [m for m in get_message_repository().find_by_conversation(session.conversation_id)]
    assert [(m.role, m.content) for m in saved] == [
        ("user", "A website support agent please"),
        ("assistant", "Here's the plan."),
    ]


async def test_a_conversation_without_a_session_is_refused(account):
    conversation = ConversationRepository().save(Conversation(title="x", agent_id=ILA_AGENT_ID, created_by=TEST_USER_EMAIL))
    session = BuilderSession(conversation_id=conversation.conversation_id, user_email=TEST_USER_EMAIL, provider="Bedrock")

    events = [event async for event in vishwakarma.VishwakarmaArchitecture().handle_message(
        agent=ila_agent(session), conversation=conversation, user_message="hi", owner_email=TEST_USER_EMAIL,
        actor_email=TEST_USER_EMAIL, actor_id=TEST_USER_EMAIL, actor_kind=ActorKind.OWNER,
    )]
    assert events[-1].event_type == SSEEventType.ERROR


def test_registry_marks_plan_and_apply_as_prompt_changing():
    registry = build_builder_tool_registry(BuilderTools(sessions=object(), messages=object()))  # type: ignore[arg-type]
    assert registry.get("plan_blueprint").spec.mutates_prompt_context
    assert registry.get("apply_blueprint").spec.mutates_prompt_context
    assert not registry.get("show_form").spec.mutates_prompt_context


# --- Routes -----------------------------------------------------------------------------------


def test_session_form_offers_the_persons_providers(test_client, auth_headers, account):
    form = test_client.get("/builder/session-form", headers=auth_headers).json()

    provider, model = form["form_inputs"]
    assert [provider["name"], model["name"]] == ["agent_provider", "agent_model"]
    # Filled in on the server, as for the create-agent form; the browser has nothing to resolve.
    assert "Bedrock" in [option["value"] for option in provider["options"]]


def test_starting_a_session_needs_a_provider_that_is_set_up(test_client, auth_headers, dynamodb_table):
    response = test_client.post("/builder/sessions", headers=auth_headers, json={"agent_provider": "Bedrock"})
    assert response.status_code == 400
    assert "Provider Configuration" in response.json()["detail"]


def test_a_session_starts_with_adas_greeting(test_client, auth_headers, account):
    created = test_client.post("/builder/sessions", headers=auth_headers, json={"agent_provider": "Bedrock"})
    assert created.status_code == 201, created.text
    conversation_id = created.json()["conversation_id"]

    conversation = ConversationRepository().find_by_id(conversation_id, TEST_USER_EMAIL)
    assert conversation.agent_id == ILA_AGENT_ID
    [greeting] = get_message_repository().find_by_conversation(conversation_id)
    assert (greeting.role, greeting.content) == ("assistant", GREETING)
    listed = test_client.get("/builder/sessions", headers=auth_headers).json()
    assert [item["conversation_id"] for item in listed] == [conversation_id]


def test_send_message_runs_ila_through_the_injected_architecture(test_client, auth_headers, session, monkeypatch):
    started: dict = {}

    def fake_start_turn(**kwargs):
        started.update(kwargs)
        raise RuntimeError("stop here")

    monkeypatch.setattr(builder_router, "start_turn", fake_start_turn)
    with pytest.raises(RuntimeError):
        test_client.post(f"/builder/{session.conversation_id}/send-message", headers=auth_headers, json={"content": "hi"})

    assert isinstance(started["architecture"], vishwakarma.VishwakarmaArchitecture)
    assert started["agent"].agent_id == ILA_AGENT_ID
    assert started["agent"].agent_architecture == "vishwakarma"


def test_send_message_to_a_conversation_that_isnt_a_build(test_client, auth_headers, account):
    response = test_client.post("/builder/not-a-build/send-message", headers=auth_headers, json={"content": "hi"})
    assert response.status_code == 404


# --- Blueprint canvas -------------------------------------------------------------------------

MEDIA_BUCKET = "innomightlabs-conversations-meta"


def _planned(account, params=PARAMS):
    validated = validate_blueprint(SITE_AGENT, params)
    return validated, plan_blueprint(validated, TEST_USER_EMAIL)


def test_the_drawing_shows_each_resource_and_how_they_connect(account):
    validated, plan = _planned(account)
    drawing = drawing_for(validated, plan, stage="plan", plan_id="abc")

    assert [(card.name, card.label, card.depth) for card in drawing.cards] == [
        ("site_kb", "Knowledge base", 0), ("assistant", "Agent", 1), ("widget", "Chat widget", 2),
    ]
    assert drawing.edges == [("site_kb", "assistant", "knowledge for"), ("assistant", "widget", "chats through")]
    assert drawing.cards[2].title == "Acme assistant widget"
    assert ("Business name", "Acme") in drawing.params
    page = render_drawing(drawing)
    assert "Draft<br>awaiting approval" in page and "Rev abc" in page


def test_what_the_person_typed_cannot_inject_markup(account):
    validated, plan = _planned(account, {**PARAMS, "business_name": "<script>alert(1)</script>"})
    page = render_drawing(drawing_for(validated, plan, stage="plan", plan_id="abc"))

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_yaml_is_escaped_then_coloured():
    highlighted = str(highlight_yaml('name: "{{ params.x }}"\n# note <b>\n'))
    assert '<span class="y-key">name</span>' in highlighted
    assert '<span class="y-tpl">{{ params.x }}</span>' in highlighted
    assert "&lt;b&gt;" in highlighted and "<b>" not in highlighted


async def test_plan_and_build_each_attach_a_blueprint_canvas(session, monkeypatch):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=MEDIA_BUCKET)
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", MEDIA_BUCKET)
    tools, state = BuilderTools(), turn_state(session)

    planned = json.loads(await tools.plan("plan_blueprint", {"yaml": SITE_AGENT, "params": PARAMS}, state))
    assert planned["type"] == "ui_form_render"
    assert planned["canvas"]["type"] == "canvas_artifact"
    assert planned["canvas"]["title"] == "Blueprint: Website support agent"

    say(session, "user", approval(planned["plan_id"]))
    built = json.loads(await tools.apply("apply_blueprint", {"plan_id": planned["plan_id"]}, state))
    assert built["applied"] is True
    assert built["canvas"]["title"] == "Built: Website support agent"


async def test_a_canvas_that_cant_be_saved_doesnt_stop_the_plan(session, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("storage down")

    monkeypatch.setattr("src.builder.canvas.ArtifactService.create_artifact", broken)
    planned = json.loads(await BuilderTools().plan("plan_blueprint", {"yaml": SITE_AGENT, "params": PARAMS}, turn_state(session)))

    assert planned["ok"] is True and planned["type"] == "ui_form_render"
    assert "canvas" not in planned


# --- Extending what exists --------------------------------------------------------------------


async def test_after_a_build_the_draft_is_pinned_to_what_was_built(session):
    tools, state = BuilderTools(), turn_state(session)
    plan_id = json.loads(await tools.plan("plan_blueprint", {"yaml": SITE_AGENT, "params": PARAMS}, state))["plan_id"]
    say(session, "user", approval(plan_id))
    built = json.loads(await tools.apply("apply_blueprint", {"plan_id": plan_id}, state))

    draft = BuilderSessionRepository().find(TEST_USER_EMAIL, session.conversation_id).draft_yaml
    assert f"id: {built['resources']['assistant']['id']}" in draft

    # Ila changes the draft and plans again: the same agent is updated, nothing new is built.
    changed = draft.replace("allow_guests: true", "allow_guests: false")
    replanned = json.loads(await tools.plan("plan_blueprint", {"yaml": changed, "params": PARAMS}, state))
    assert [step["action"] for step in replanned["steps"]] == ["unchanged", "unchanged", "update"]


async def test_ila_can_find_and_load_an_existing_agent(session):
    tools, state = BuilderTools(), turn_state(session)
    plan_id = json.loads(await tools.plan("plan_blueprint", {"yaml": SITE_AGENT, "params": PARAMS}, state))["plan_id"]
    say(session, "user", approval(plan_id))
    built = json.loads(await tools.apply("apply_blueprint", {"plan_id": plan_id}, state))
    agent_id = built["resources"]["assistant"]["id"]

    [listed] = json.loads(await tools.list_agents("list_my_agents", {}, state))["agents"]
    assert listed == {
        "agent_id": agent_id, "name": "Acme assistant", "description": "The agent visitors chat with.",
        "knowledge_bases": 1, "skills": ["lead_capture"], "widget_keys": 1,
    }

    loaded = json.loads(await tools.load_agent("load_agent", {"agent_id": agent_id}, state))
    assert loaded["loaded"] is True
    draft = BuilderSessionRepository().find(TEST_USER_EMAIL, session.conversation_id).draft_yaml
    assert f"id: {agent_id}" in draft
    # In its kit, the draft is the kit's last version with its params.
    replanned = json.loads(await tools.plan("plan_blueprint", {"yaml": draft}, state))
    assert replanned["ok"] is True, replanned
    assert {step["action"] for step in replanned["steps"]} == {"unchanged"}
    # Nothing to approve when nothing changes.
    assert replanned["nothing_to_change"] is True
    assert "type" not in replanned and "plan_id" not in replanned

    missing = json.loads(await tools.load_agent("load_agent", {"agent_id": "nope"}, state))
    assert missing["loaded"] is False


async def test_ila_names_what_a_plan_removes(session):
    """An agent loaded from outside a kit: what it was is the baseline, so leaving a skill out uninstalls it."""
    validated = validate_blueprint(SITE_AGENT, PARAMS)
    built = apply_blueprint(validated, plan_blueprint(validated, TEST_USER_EMAIL), TEST_USER_EMAIL)
    tools, state = BuilderTools(), turn_state(session)
    assert json.loads(await tools.load_agent("load_agent", {"agent_id": built.resources["assistant"].id}, state))["loaded"]
    draft = BuilderSessionRepository().find(TEST_USER_EMAIL, session.conversation_id).draft_yaml
    document = yaml.safe_load(draft)
    document["resources"]["agent"]["skills"] = []

    result = json.loads(await tools.plan("plan_blueprint", {"yaml": yaml.safe_dump(document, sort_keys=False)}, state))
    assert result["removals"] == ["uninstall skill lead capture"]
    assert "can't be undone" in result["next"]
    assert "This removes" in result["form"]["form_inputs"][0]["attr"]["help_text"]