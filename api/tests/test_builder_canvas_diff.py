"""The plan's drawing shows a long text it rewrites, before and after, so the person approves the exact words."""

import json

import yaml

from src.blueprints.executor import apply_blueprint
from src.blueprints.planner import plan_blueprint
from src.blueprints.validator import validate_blueprint
from src.builder.canvas import _diff, drawing_for, render_drawing
from src.builder.repository import BuilderSessionRepository
from src.builder.tools import BuilderTools
from tests.mock_data import test_owner as _test_owner
from tests.test_builder_ila import PARAMS, SITE_AGENT, account, session, turn_state  # noqa: F401

TEST_OWNER = _test_owner()
RULES = [f"Rule {n}: answer plainly." for n in range(1, 21)]


def test_a_diff_keeps_a_little_around_each_change_and_leaves_the_rest_out():
    after = [*RULES[:9], "Rule 10: answer plainly, and mention the refund policy.", *RULES[10:]]

    diff = _diff("Desk", "instructions", "\n".join(RULES), "\n".join(after))

    assert (diff.added, diff.removed) == (1, 1)
    assert diff.lines == (
        ("gap", ""),
        ("same", "Rule 8: answer plainly."),
        ("same", "Rule 9: answer plainly."),
        ("remove", "Rule 10: answer plainly."),
        ("add", "Rule 10: answer plainly, and mention the refund policy."),
        ("same", "Rule 11: answer plainly."),
        ("same", "Rule 12: answer plainly."),
        ("gap", ""),
    )


def test_a_change_at_the_start_needs_no_gap_before_it():
    diff = _diff("Desk", "instructions", "\n".join(RULES[:3]), "\n".join(["Be brief.", *RULES[:3]]))

    assert diff.lines[0] == ("add", "Be brief."), "nothing left out before it"


def built_site_agent() -> str:
    """The site agent, built; its agent's id."""
    validated = validate_blueprint(SITE_AGENT, PARAMS)
    built = apply_blueprint(validated, plan_blueprint(validated, TEST_OWNER), TEST_OWNER)
    return built.resources["assistant"].id


async def test_the_plan_shows_the_instructions_it_rewrites(session):  # noqa: F811
    agent_id = built_site_agent()
    tools, state = BuilderTools(), turn_state(session)
    await tools.add_to_draft("add_to_draft", {"page_id": f"account/Agent/{agent_id}"}, state)
    document = yaml.safe_load(BuilderSessionRepository().find(TEST_OWNER.member_pk, session.conversation_id).draft_yaml)
    agent = next(spec for spec in document["resources"].values() if spec["kind"] == "Agent")
    line = "Answer visitors' questions using the website knowledge base, and keep answers short and friendly."
    assert line in agent["instructions"]
    agent["instructions"] = agent["instructions"].replace(line, "Answer visitors' questions from the website, in two sentences at most.")

    result = json.loads(await tools.plan("plan_blueprint", {"yaml": yaml.safe_dump(document, sort_keys=False)}, state))

    assert result["ok"] is True, result
    assert "before and after" in result["next"]
    planned = BuilderSessionRepository().find(TEST_OWNER.member_pk, session.conversation_id)
    validated = validate_blueprint(planned.draft_yaml, planned.draft_params)
    drawing = drawing_for(validated, plan_blueprint(validated, TEST_OWNER), stage="plan", plan_id="p1")
    [diff] = drawing.text_diffs
    assert (diff.title, diff.field, diff.added, diff.removed) == ("Acme assistant", "instructions", 1, 1)
    assert ("remove", line) in diff.lines

    page = render_drawing(drawing)
    assert 'data-tab="changes" aria-selected="true"' in page, "it opens on the change"
    assert '<span class="d-line d-add">Answer visitors&#39; questions from the website' in page


def test_nothing_to_show_when_no_long_text_changes(session):  # noqa: F811
    built_site_agent()
    renamed = validate_blueprint(SITE_AGENT.replace("allow_guests: true", "allow_guests: false"), PARAMS)

    drawing = drawing_for(renamed, plan_blueprint(renamed, TEST_OWNER), stage="plan", plan_id="p1")

    assert drawing.text_diffs == []
    page = render_drawing(drawing)
    assert 'data-tab="changes"' not in page and 'data-tab="drawing" aria-selected="true"' in page


def test_the_built_drawing_opens_on_the_blueprint(session):  # noqa: F811
    built_site_agent()
    changed = validate_blueprint(SITE_AGENT.replace("keep answers short and friendly", "keep answers short"), PARAMS)

    page = render_drawing(drawing_for(changed, plan_blueprint(changed, TEST_OWNER), stage="built", plan_id="p1"))

    assert 'data-tab="changes" aria-selected="false"' in page and 'data-tab="drawing" aria-selected="true"' in page
