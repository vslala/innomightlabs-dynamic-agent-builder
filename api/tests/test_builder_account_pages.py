"""The book's Your account branch: nested pages, made when opened, from every resource kind."""

import ast
import json
from pathlib import Path

import pytest

from src.agents.architectures.vishwakarma_prompt import build_vishwakarma_system_prompt
from src.agents.book import Book, Chapter, Page
from src.blueprints.book import blueprint_book
from src.blueprints.executor import apply_blueprint
from src.blueprints.kinds import RESOURCE_KINDS
from src.blueprints.planner import plan_blueprint
from src.blueprints.validator import validate_blueprint
from src.builder.repository import BuilderSessionRepository
from src.builder.tools import BuilderTools
from tests.mock_data import test_owner as _test_owner
from tests.test_builder_ila import PARAMS, SITE_AGENT, account, session, turn_state  # noqa: F401

TEST_OWNER = _test_owner()


# --- Nested pages and resolvers ---------------------------------------------------------------


class Counting:
    """A resolver that says how often it was asked."""

    prefix = "mine/"

    def __init__(self) -> None:
        self.asked: list[str] = []

    def resolve(self, page_id: str) -> Page | None:
        self.asked.append(page_id)
        return Page(id=page_id, title="Mine", summary="Made when opened.", body=f"About {page_id}") if page_id != "mine/gone" else None

    def searchable(self, prefix: str) -> list[Page]:
        return []


def tree_book(resolver: Counting) -> Book:
    steps = Page(id="kind/Automation/steps", title="Steps", summary="What steps can do.", body="Steps in detail.")
    return Book(
        [
            Chapter(title="Kinds", intro="", pages=(
                Page(id="kind/Automation", title="Automation", summary="Runs by itself.", body="Its fields.", children=(steps,)),
            )),
            Chapter(title="Mine", intro="", pages=(Page(id="mine/list", title="Mine", summary="Open to list.", body=""),)),
        ],
        resolvers=[resolver],
    )


def test_a_nested_page_is_opened_by_its_id():
    book = tree_book(Counting())

    assert book.get("kind/Automation/steps").body == "Steps in detail."
    assert "kind/Automation/steps" in book.page_ids
    assert book.search("steps")[0].id == "kind/Automation/steps"


def test_a_resolver_makes_its_pages_when_opened_and_once_per_book():
    resolver = Counting()
    book = tree_book(resolver)
    assert resolver.asked == [], "building the book reads nothing"

    assert book.get("mine/list").body == "About mine/list", "the index line isn't the page"
    book.get("mine/list")
    assert book.get("mine/gone") is None

    assert resolver.asked == ["mine/list", "mine/gone"]
    assert [page.id for page in book.open(["mine/list", "mine/gone"]).pages] == ["mine/list"]


def test_search_looks_through_what_a_resolver_offers_under_the_prefix():
    class Offering(Counting):
        def searchable(self, prefix: str) -> list[Page]:
            self.asked.append(f"search {prefix}")
            return [Page(id="mine/innomight", title="Innomight helper", summary="One of mine.", body="")]

    resolver = Offering()
    book = tree_book(resolver)

    assert [page.id for page in book.search("innomight")] == ["mine/innomight"]
    assert book.search("innomight", prefix="kind/") == [], "a prefix elsewhere doesn't ask the resolver"
    assert resolver.asked == ["search "]
    assert [page.id for page in book.search("", prefix="kind/Automation")] == ["kind/Automation/steps"]
    assert book.search("") == []


# --- Every kind can be read -------------------------------------------------------------------


@pytest.mark.parametrize("kind", RESOURCE_KINDS, ids=lambda kind: kind.kind)
def test_every_kind_lists_and_reads_the_owners_resources(kind, dynamodb_table):
    """A new kind is readable in the book only through these, so leaving one out fails here."""
    assert kind.existing(TEST_OWNER) == []
    assert kind.read(TEST_OWNER, "no-such-id") is None
    assert blueprint_book(owner=TEST_OWNER).get(f"account/{kind.kind}") is not None


def test_the_account_branch_is_only_in_a_book_for_someone(dynamodb_table):
    assert "account/Agent" not in blueprint_book().page_ids
    assert "account/Agent" in blueprint_book(owner=TEST_OWNER).page_ids


def built_site_agent():
    validated = validate_blueprint(SITE_AGENT, PARAMS)
    return apply_blueprint(validated, plan_blueprint(validated, TEST_OWNER), TEST_OWNER)


def test_a_knowledge_base_and_a_widget_are_pages_too(session):  # noqa: F811
    built = built_site_agent()
    book = blueprint_book(owner=TEST_OWNER)
    agent_id, key_id = built.resources["assistant"].id, built.resources["widget"].id

    knowledge = book.get(f"account/KnowledgeBase/{built.resources['site_kb'].id}")
    assert "max_pages:" in knowledge.body, "its crawl, as a blueprint writes it"
    widget = book.get(f"account/WidgetKey/{key_id}")
    assert "https://acme.example" in widget.body and f"`account/Agent/{agent_id}`" in widget.body
    assert f"`account/WidgetKey/{key_id}`" in book.get(f"account/Agent/{agent_id}").body


def test_someone_elses_resources_are_not_pages(session):  # noqa: F811
    built = built_site_agent()
    other = _test_owner("someone-else@example.com")

    assert blueprint_book(owner=other).get(f"account/Agent/{built.resources['assistant'].id}") is None
    assert blueprint_book(owner=other).get("account/Agent").children == ()


async def test_ila_finds_the_persons_resources_by_name(session, monkeypatch):  # noqa: F811
    built = built_site_agent()
    agent_id = built.resources["assistant"].id
    tools, state = BuilderTools(), turn_state(session)

    async def search(**tool_input) -> list[str]:
        result = json.loads(await tools.search_book("search_book", tool_input, state))
        return [page["id"] for page in result["pages"]]

    assert f"account/Agent/{agent_id}" in await search(query="acme assistant")
    assert await search(query="acme assistant", prefix="account/Agent") == [f"account/Agent/{agent_id}"]
    assert await search(prefix="account/WidgetKey") == [f"account/WidgetKey/{built.resources['widget'].id}"]
    assert await search(query="acme assistant", prefix="skill/") == []

    read: list[str] = []
    for kind in RESOURCE_KINDS:
        original = type(kind).existing
        monkeypatch.setattr(type(kind), "existing", lambda self, owner, original=original: read.append(self.kind) or original(self, owner))
    await search(query="acme", prefix="account/Agent")
    assert read == ["Agent"], "a narrow prefix reads one kind"


# --- What Ila sees ----------------------------------------------------------------------------


async def test_an_open_page_lists_the_pages_under_it_in_her_prompt(session):  # noqa: F811
    built = built_site_agent()
    agent_id = built.resources["assistant"].id
    tools, state = BuilderTools(), turn_state(session)
    await tools.open_book_pages("open_pages", {"page_ids": ["account/Agent"]}, state)
    current = BuilderSessionRepository().find(TEST_OWNER.member_pk, session.conversation_id)

    prompt = build_vishwakarma_system_prompt(book=blueprint_book(owner=TEST_OWNER), session=current, retention=3)

    assert "## Your account" in prompt
    assert "Pages under it, to open when you need them:" in prompt
    assert f"- `account/Agent/{agent_id}`: Acme assistant." in prompt


async def test_adding_a_widget_names_its_agent_as_the_draft_does(session):  # noqa: F811
    built = built_site_agent()
    tools, state = BuilderTools(), turn_state(session)
    agent_id, key_id = built.resources["assistant"].id, built.resources["widget"].id

    await tools.add_to_draft("add_to_draft", {"page_id": f"account/Agent/{agent_id}"}, state)
    added = json.loads(await tools.add_to_draft("add_to_draft", {"page_id": f"account/WidgetKey/{key_id}"}, state))

    draft = BuilderSessionRepository().find(TEST_OWNER.member_pk, session.conversation_id).draft_yaml
    assert added["resource"] == "widget", "the same key, so it stays under the name the agent's export gave it"
    assert draft.count(f"id: {key_id}") == 1


# --- Ila reaches features only through their kinds --------------------------------------------

#: Feature modules whose data Ila reads through the resource kinds, never directly
THROUGH_KINDS = ("src.agents.repository", "src.leads", "src.automations", "src.apikeys", "src.skills.repository")


def test_ilas_tools_read_features_only_through_their_kinds():
    """So a change to a feature's storage is made once, in its kind, and every page Ila reads follows it."""
    builder = Path(__file__).resolve().parents[1] / "src" / "builder"
    reaching = []
    for path in builder.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(THROUGH_KINDS):
                reaching.append(f"{path.name}: {node.module}")
    assert reaching == []
