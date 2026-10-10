"""What plan_blueprint tells Ila is decided by gates in order; issues say who fixes them; and everything the system
asks the person goes through one list of requirements."""

import json

import yaml

from src.blueprints.catalog import example_yaml
from src.blueprints.issues import BlueprintInvalid, IssueOwner
from src.blueprints.validator import validate_blueprint
from src.builder.models import BuilderSession
from src.builder.plan_gates import PLAN_GATES, AuthorIssues, AwaitApproval, Blocked, NeedsPerson, NothingToChange
from src.builder.requirements import REQUIREMENTS, AccountConnection, SkillSettings, absorb_answers
from src.builder.tools import BuilderTools
from tests.mock_data import TEST_USER_EMAIL
from tests.test_builder_ila import PARAMS, account, session, turn_state  # noqa: F401

SITE_AGENT = example_yaml("site-agent") or ""


def with_skills(*entries: dict) -> str:
    document = yaml.safe_load(SITE_AGENT)
    document["resources"]["assistant"]["skills"] += list(entries)
    return yaml.safe_dump(document, sort_keys=False)


async def plan(session_: BuilderSession, tool_input: dict) -> dict:
    return json.loads(await BuilderTools().plan("plan_blueprint", tool_input, turn_state(session_)))


def test_the_gates_and_requirements_run_in_order():
    assert [type(gate) for gate in PLAN_GATES] == [AuthorIssues, NeedsPerson, Blocked, NothingToChange, AwaitApproval]
    # The person signs in first, then gives any settings, then sees the plan.
    assert [type(requirement) for requirement in REQUIREMENTS] == [AccountConnection, SkillSettings]


def test_a_missing_setting_only_the_person_knows_is_theirs_to_settle():
    text = with_skills({"id": "send_email"}, {"id": "agent_invocation", "config": {"target_agent_id": "nobody"}})
    try:
        validate_blueprint(text, PARAMS)
    except BlueprintInvalid as e:
        owners = {issue.path: issue.owner for issue in e.issues}
    else:  # pragma: no cover
        raise AssertionError("expected issues")
    assert owners["resources.assistant.skills[1].config"] == IssueOwner.PERSON  # send_email's recipients
    assert all(owner == IssueOwner.AUTHOR for path, owner in owners.items() if "skills[2]" in path)


async def test_ila_fixes_her_own_issues_before_the_person_is_asked(session):  # noqa: F811
    text = with_skills({"id": "send_email"}).replace("agent: assistant", "agent: assistnt")
    result = await plan(session, {"yaml": text, "params": PARAMS})
    assert result["ok"] is False and "needs_input" not in result
    assert [issue["path"] for issue in result["issues"]] == ["resources.widget.agent"]
    assert all("owner" not in issue for issue in result["issues"])  # who owns it is the system's business

    # Fixed, only the person's setting is left: the system asks them.
    result = await plan(session, {"yaml": with_skills({"id": "send_email"}), "params": PARAMS})
    assert result["needs_input"]["skill"] == "Send Email"


async def test_the_answer_to_whatever_was_asked_goes_through_the_requirements(session):  # noqa: F811
    result = await plan(session, {"yaml": with_skills({"id": "send_email"}), "params": PARAMS})
    label = result["form"]["form_name"]
    current = BuilderTools().sessions.find(TEST_USER_EMAIL, session.conversation_id)
    message = f'<form_submission label="{label}">\n- to: a@acme.example\n</form_submission>\n\nFields:\n- to="a@acme.example"'
    assert absorb_answers(current, message)
    assert "a@acme.example" in current.draft_yaml
    assert not absorb_answers(current, "just chatting")
