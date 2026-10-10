"""The system, not Ila, asks the person for a skill's settings: one form per skill, from its manifest."""

import json

import yaml

from src.agents.agentic_loop import TurnComplete
from src.agents.architectures import vishwakarma
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.blueprints.catalog import example_yaml
from src.builder.ila import ila_agent
from src.builder.models import BuilderSession, PendingInput
from src.builder.repository import BuilderSessionRepository
from src.blueprints.draft import Draft
from src.builder.skill_inputs import absorb_submission, missing_inputs, submitted_values
from src.builder.tools import BuilderTools
from src.conversations.repository import ConversationRepository
from src.llm.events import SSEEvent, SSEEventType
from src.skills.models import ActorKind
from tests.mock_data import TEST_USER_EMAIL
from tests.test_builder_ila import PARAMS, account, session, turn_state  # noqa: F401

SITE_AGENT = example_yaml("site-agent") or ""


def with_skills(*entries: dict) -> str:
    document = yaml.safe_load(SITE_AGENT)
    document["resources"]["assistant"]["skills"] += list(entries)
    return yaml.safe_dump(document, sort_keys=False)


def submission(label: str, **values: str) -> str:
    """What the chat sends when the person submits a form (ConversationDetail.handleFormSubmit)."""
    shown = "\n".join(f"- {name}: {value}" for name, value in values.items())
    fields = "\n".join(f'- {name}="{value}"' for name, value in values.items())
    return f'<form_submission label="{label}">\n{shown}\n</form_submission>\n\nFields:\n{fields}'


async def plan(session_: BuilderSession, tool_input: dict) -> dict:
    return json.loads(await BuilderTools().plan("plan_blueprint", tool_input, turn_state(session_)))


def reload(session_: BuilderSession) -> BuilderSession:
    return BuilderSessionRepository().find(TEST_USER_EMAIL, session_.conversation_id)


def answer(session_: BuilderSession, **values: str) -> BuilderSession:
    """The person submits the form the session is waiting on; the turn absorbs it, as the architecture does."""
    current = reload(session_)
    assert absorb_submission(current, submission(current.pending_input.label, **values))
    return BuilderSessionRepository().save(current)


# --- What's missing ----------------------------------------------------------------------------


def test_only_required_settings_the_draft_lacks_are_missing():
    text = with_skills(
        {"id": "send_email"},
        {"id": "send_email", "config": {"to": "a@acme.example"}},
        {"id": "aws_cli"},  # needs a secret, so it's never asked in the chat
    )
    [item] = missing_inputs(Draft(text), PARAMS)
    assert (item.key, item.skill_id, item.index) == ("assistant/send_email/0", "send_email", 1)
    assert [field.name for field in item.fields] == ["to"]
    assert item.label == "Set up Send Email for Acme assistant"


def test_a_second_entry_of_the_same_skill_has_its_own_form():
    labels = [item.label for item in missing_inputs(Draft(with_skills({"id": "send_email"}, {"id": "send_email"})))]
    assert labels[1].endswith("assistant (2)")


def test_answers_fill_in_only_what_the_draft_lacks():
    text = with_skills({"id": "send_email"})
    answers = {"assistant/send_email/0": {"to": "a@acme.example"}}
    filled = Draft(text).with_skill_settings(answers)
    assert filled.data["resources"]["assistant"]["skills"][1]["config"] == {"to": "a@acme.example"}
    # Multi-line text stays readable, and the draft it came from is left as it was.
    assert "instructions: |" in filled.text
    assert Draft(text).with_skill_settings({}).text == text


def test_a_submission_is_read_only_for_its_own_form():
    message = submission("Set up Send Email for Acme assistant", to="a@acme.example")
    assert submitted_values(message, "Set up Send Email for Acme assistant") == {"to": "a@acme.example"}
    assert submitted_values(message, "Approve plan 123") is None
    assert submitted_values("just chatting", "Set up Send Email for Acme assistant") is None


# --- The flow ----------------------------------------------------------------------------------


async def test_planning_a_skill_without_its_settings_asks_the_person(session):  # noqa: F811
    result = await plan(session, {"yaml": with_skills({"id": "send_email"}), "params": PARAMS})

    assert result["ok"] is False and result["needs_input"]["skill"] == "Send Email"
    assert result["type"] == "ui_form_render"
    assert result["form"]["form_name"].startswith("Set up Send Email for")
    [field] = result["form"]["form_inputs"]
    assert (field["name"], field["label"]) == ("to", "Recipient emails")
    saved = reload(session)
    assert saved.pending_input.label == result["form"]["form_name"] and saved.plan_id is None

    # The person answers; the next plan, with no arguments, goes ahead with their answer in the draft.
    answer(session, to="sales@acme.example")
    result = await plan(session, {})
    assert result["ok"] is True and result["plan_id"]
    assert "sales@acme.example" in reload(session).draft_yaml
    assert reload(session).pending_input is None


async def test_ila_rewriting_the_draft_keeps_the_persons_answers(session):  # noqa: F811
    text = with_skills({"id": "send_email"})
    await plan(session, {"yaml": text, "params": PARAMS})
    answer(session, to="sales@acme.example")

    result = await plan(session, {"yaml": text.replace("short and friendly", "short"), "params": PARAMS})
    assert result["ok"] is True
    assert "sales@acme.example" in reload(session).draft_yaml


async def test_a_bad_answer_asks_again_with_the_reason(session):  # noqa: F811
    await plan(session, {"yaml": with_skills({"id": "send_email"}), "params": PARAMS})
    answer(session, to="not an email")
    error = reload(session).pending_input.error
    assert error and reload(session).skill_inputs == {}

    result = await plan(session, {})
    assert result["needs_input"]["skill"] == "Send Email"
    assert result["form"]["form_inputs"][0]["attr"]["help_text"].startswith(error)
    assert reload(session).pending_input.error is None  # shown once, on the form


async def test_skills_are_asked_one_at_a_time_in_order(session):  # noqa: F811
    text = with_skills({"id": "send_email"}, {"id": "wordpress_search"})

    first = await plan(session, {"yaml": text, "params": PARAMS})
    assert first["needs_input"] == {"skill": "Send Email", "agent": "Acme assistant", "skills_left": 2}
    # The form says what the skill is for, so the person knows why they're asked.
    assert first["form"]["form_inputs"][0]["attr"]["help_text"].startswith("Acme assistant will use Send Email:")
    answer(session, to="sales@acme.example")

    second = await plan(session, {})
    assert second["needs_input"]["skill"] == "WordPress Search"
    answer(session, site_url="https://blog.acme.example")

    third = await plan(session, {})
    assert third["ok"] is True, third


async def test_the_person_is_never_asked_for_the_builds_design(session):  # noqa: F811
    """Which agent a skill calls, and when, are Ila's to write: a missing one is an issue for her, not a form."""
    result = await plan(session, {"yaml": with_skills({"id": "agent_invocation"}), "params": PARAMS})
    assert "needs_input" not in result and result["ok"] is False
    assert {issue["page"] for issue in result["issues"]} == {"skill/agent_invocation"}
    assert reload(session).pending_input is None


async def test_other_issues_go_to_ila_before_the_person_is_asked(session):  # noqa: F811
    text = with_skills({"id": "send_email"}).replace("mode: site", "mode: everything")
    result = await plan(session, {"yaml": text, "params": PARAMS})
    assert "issues" in result and "needs_input" not in result
    assert reload(session).pending_input is None


async def test_loading_an_agent_forgets_answers_for_the_old_draft(session):  # noqa: F811
    stale = reload(session)
    stale.skill_inputs = {"agent/send_email/0": {"to": "old@acme.example"}}
    stale.pending_input = PendingInput(key="agent/send_email/0", label="Set up Send Email for Old")
    BuilderSessionRepository().save(stale)
    agent = AgentRepository().save(Agent(
        agent_name="Docs", agent_architecture="krishna-memgpt", agent_provider="Bedrock",
        agent_persona="Docs.", created_by=TEST_USER_EMAIL,
    ))
    await BuilderTools().load_agent("load_agent", {"agent_id": agent.agent_id}, turn_state(session))
    assert reload(session).skill_inputs == {} and reload(session).pending_input is None


async def test_the_turn_takes_the_answers_before_ila_sees_it(session, monkeypatch):  # noqa: F811
    await plan(session, {"yaml": with_skills({"id": "send_email"}), "params": PARAMS})
    label = reload(session).pending_input.label
    prompts: list[str] = []

    async def fake_loop(**kwargs):
        prompts.append(kwargs["context"][0]["content"])
        yield SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content="Thanks.")
        yield TurnComplete(full_text="Thanks.")

    async def fake_provider_session(agent, **kwargs):
        return type("Session", (), {"provider": object(), "credentials": {}})()

    monkeypatch.setattr(vishwakarma, "run_agentic_tool_loop", fake_loop)
    monkeypatch.setattr(vishwakarma, "open_provider_session", fake_provider_session)
    conversation = ConversationRepository().find_by_id(session.conversation_id, TEST_USER_EMAIL)
    async for _ in vishwakarma.VishwakarmaArchitecture().handle_message(
        agent=ila_agent(session), conversation=conversation,
        user_message=submission(label, to="sales@acme.example"),
        owner_email=TEST_USER_EMAIL, actor_email=TEST_USER_EMAIL, actor_id=TEST_USER_EMAIL, actor_kind=ActorKind.OWNER,
    ):
        pass

    assert "sales@acme.example" in prompts[0]  # in the draft Ila's prompt shows
    assert reload(session).skill_inputs == {"assistant/send_email/0": {"to": "sales@acme.example"}}


async def test_a_form_no_longer_needed_stops_being_waited_on(session):  # noqa: F811
    stale = reload(session)
    stale.pending_input = PendingInput(key="assistant/agent_invocation/3", label="Set up Invoke Agent for Team lead (4)")
    BuilderSessionRepository().save(stale)
    await plan(session, {"yaml": with_skills({"id": "agent_invocation"}), "params": PARAMS})
    assert reload(session).pending_input is None
