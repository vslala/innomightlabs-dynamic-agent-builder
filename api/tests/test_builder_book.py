"""Ada's blueprint book: pages generated from the code, an index in her prompt, and pages kept open for a few turns."""

import json

import pytest
import yaml

from src.agents.agentic_loop import PromptRefreshNeeded, TurnComplete
from src.agents.architectures import vishwakarma
from src.agents.book import open_pages, pages_in_view, turns_left
from src.blueprints.book import GUIDE, blueprint_book, page_for_issue, skill_example
from src.blueprints.catalog import example_names, example_yaml
from src.blueprints.kinds import RESOURCE_KINDS
from src.blueprints.skills_schema import skill_variants
from src.blueprints.validator import validate_blueprint
from src.builder.ada import ada_agent
from src.builder.repository import BuilderSessionRepository
from src.builder.tools import BuilderTools
from src.config import settings
from src.conversations.repository import ConversationRepository
from src.llm.events import SSEEvent, SSEEventType
from src.skills.models import ActorKind
from tests.mock_data import TEST_USER_EMAIL
from tests.test_builder_ada import PARAMS, SITE_AGENT, account, session, turn_state  # noqa: F401

BOOK = blueprint_book()


# --- The pages ---------------------------------------------------------------------------------


def test_every_kind_skill_and_example_has_a_page():
    ids = set(BOOK.page_ids)
    assert GUIDE in ids
    assert {f"kind/{kind.kind}" for kind in RESOURCE_KINDS} <= ids
    assert {f"skill/{skill_id}" for skill_id in skill_variants()} <= ids
    assert {f"recipe/{name}" for name in example_names()} <= ids


def test_every_page_can_be_found_from_the_index():
    for chapter in BOOK.chapters:
        for page in chapter.pages:
            assert page.title and page.summary and page.body, page.id
    for kind in RESOURCE_KINDS:
        assert BOOK.get(f"kind/{kind.kind}").use_when, f"{kind.kind} needs a use_when line"


def test_a_kind_page_has_its_fields_nested_models_and_an_example():
    page = BOOK.get("kind/KnowledgeBase").body
    assert "| `crawl` |" in page
    assert "### CrawlSpec" in page and "| `max_pages` |" in page
    assert "`crawl_job_id`" in page  # what outputs can use
    assert "kind: KnowledgeBase\n  description: The documentation" in page.split("### Example")[1]


def test_every_kind_has_an_example_from_the_recipes():
    for kind in RESOURCE_KINDS:
        assert "### Example" in BOOK.get(f"kind/{kind.kind}").body, kind.kind


def test_a_skill_example_is_a_valid_skill_entry():
    variant = skill_variants()["html_canvas"]
    entry = yaml.safe_load(skill_example(variant))["skills"]
    text = yaml.safe_load(SITE_AGENT)
    text["resources"]["assistant"]["skills"] = entry
    validate_blueprint(yaml.safe_dump(text, sort_keys=False), PARAMS)


def test_skills_that_cant_be_built_say_so_in_the_index():
    assert "can't go in a blueprint" in BOOK.get("skill/aws_cli").note
    not_ready = blueprint_book(ready={"google_mail": False})
    assert "NOT READY" in not_ready.get("skill/google_mail").note
    assert BOOK.get("skill/google_mail").note == ""


def test_search_routes_on_what_the_person_asks_for():
    assert BOOK.search("capture leads with a form")[0].id == "skill/lead_capture"
    assert BOOK.search("chat bubble on my website")[0].id == "kind/WidgetKey"
    assert BOOK.search("") == []


def test_opening_an_unknown_page_suggests_the_closest():
    opened = BOOK.open(["kind/Agent", "skill/lead_captur"])
    assert [page.id for page in opened.pages] == ["kind/Agent"]
    assert opened.unknown == ["skill/lead_captur"]
    assert "skill/lead_capture" in opened.suggestions


@pytest.mark.parametrize(
    "path, page",
    [
        ("metadata.title", GUIDE),
        ("resources.widget.allowed_origins", "kind/WidgetKey"),
        ("resources.assistant.skills[0].available_to", "skill/lead_capture"),
        ("resources.nope.kind", GUIDE),
    ],
)
def test_an_issue_points_at_the_page_that_explains_it(path, page):
    assert page_for_issue(path, SITE_AGENT, BOOK) == page


# --- Retention ---------------------------------------------------------------------------------


def test_a_page_stays_open_for_the_retention_turns():
    opened = open_pages({}, ["kind/Agent"], turn=1)
    assert [pages_in_view(opened, turn, retention=3) for turn in (1, 2, 3, 4)] == [
        ["kind/Agent"], ["kind/Agent"], ["kind/Agent"], [],
    ]
    assert [turns_left(1, turn, 3) for turn in (1, 2, 3)] == [2, 1, 0]


def test_opening_again_keeps_it_longer():
    opened = open_pages(open_pages({}, ["kind/Agent"], turn=1), ["kind/Agent"], turn=3)
    assert pages_in_view(opened, 5, retention=3) == ["kind/Agent"]


def test_a_retention_of_zero_still_shows_the_page_in_its_own_turn():
    opened = open_pages({}, ["kind/Agent"], turn=4)
    assert pages_in_view(opened, 4, retention=0) == ["kind/Agent"]
    assert pages_in_view(opened, 5, retention=0) == []


# --- Ada's tools -------------------------------------------------------------------------------


async def test_open_pages_records_the_pages_on_the_session(session):  # noqa: F811
    session.turn = 2
    BuilderSessionRepository().save(session)
    result = json.loads(await BuilderTools().open_book_pages(
        "open_pages", {"page_ids": ["kind/Agent", "skill/lead_captur"]}, turn_state(session)
    ))
    assert result["opened"] == ["kind/Agent"]
    assert result["did_you_mean"][0] == "skill/lead_capture"
    saved = BuilderSessionRepository().find(TEST_USER_EMAIL, session.conversation_id)
    assert saved.opened_pages == {"kind/Agent": 2}


async def test_search_book_returns_pages_to_open(session):  # noqa: F811
    result = json.loads(await BuilderTools().search_book("search_book", {"query": "website chat widget"}, turn_state(session)))
    assert result["pages"][0]["id"] == "kind/WidgetKey"


async def test_plan_issues_open_the_pages_that_explain_them(session):  # noqa: F811
    broken = SITE_AGENT.replace("available_to: [visitor, guest]", "available_to: [everyone]")
    result = json.loads(await BuilderTools().plan("plan_blueprint", {"yaml": broken, "params": PARAMS}, turn_state(session)))
    assert result["ok"] is False
    assert any(issue.get("page") == "skill/lead_capture" for issue in result["issues"])
    saved = BuilderSessionRepository().find(TEST_USER_EMAIL, session.conversation_id)
    assert "skill/lead_capture" in saved.opened_pages


# --- Across turns ------------------------------------------------------------------------------


async def _turn(session, monkeypatch, *, open_ids=()):  # noqa: F811
    """Run one Ada turn; the fake model opens `open_ids`. Returns the prompts it saw."""
    prompts: list[str] = []

    async def fake_loop(**kwargs):
        prompts.append(kwargs["context"][0]["content"])
        if open_ids:
            outcome = await kwargs["tool_router"].execute(
                tool_name="open_pages", tool_input={"page_ids": list(open_ids)}, tool_use_id="t1", state=kwargs["state"]
            )
            assert outcome.refresh_prompt
            yield PromptRefreshNeeded()
            prompts.append(kwargs["context"][0]["content"])
        yield SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content="Ok.")
        yield TurnComplete(full_text="Ok.")

    async def fake_provider_session(agent, **kwargs):
        return type("Session", (), {"provider": object(), "credentials": {}})()

    monkeypatch.setattr(vishwakarma, "run_agentic_tool_loop", fake_loop)
    monkeypatch.setattr(vishwakarma, "open_provider_session", fake_provider_session)
    conversation = ConversationRepository().find_by_id(session.conversation_id, TEST_USER_EMAIL)
    async for _ in vishwakarma.VishwakarmaArchitecture().handle_message(
        agent=ada_agent(session),
        conversation=conversation,
        user_message="Hi",
        owner_email=TEST_USER_EMAIL,
        actor_email=TEST_USER_EMAIL,
        actor_id=TEST_USER_EMAIL,
        actor_kind=ActorKind.OWNER,
    ):
        pass
    return prompts


PAGE_HEADING = "# Chat widget (`kind/WidgetKey`"


@pytest.mark.parametrize("retention, turns_shown", [(3, 3), (2, 2), (1, 1)])
async def test_an_opened_page_leaves_the_prompt_after_the_configured_turns(
    session, monkeypatch, retention, turns_shown  # noqa: F811
):
    monkeypatch.setattr(settings, "ada_page_retention_turns", retention)
    first = await _turn(session, monkeypatch, open_ids=["kind/WidgetKey"])
    assert PAGE_HEADING not in first[0]
    assert PAGE_HEADING in first[1]  # opened mid-turn: in the refreshed prompt straight away

    later = [(await _turn(session, monkeypatch))[0] for _ in range(3)]
    shown = 1 + sum(PAGE_HEADING in prompt for prompt in later)
    assert shown == turns_shown
    saved = BuilderSessionRepository().find(TEST_USER_EMAIL, session.conversation_id)
    assert saved.turn == 4
    assert saved.opened_pages == {}  # closed pages are dropped from the session


def test_examples_still_validate_as_recipes():
    for name in example_names():
        assert BOOK.get(f"recipe/{name}").body.count(example_yaml(name).strip()) == 1
