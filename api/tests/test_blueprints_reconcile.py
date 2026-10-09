"""The reconciler: one three-way comparison over the rules each spec field declares."""

from itertools import product
from typing import Annotated

import pytest
from pydantic import BaseModel, Field

from src.blueprints.diff import Each, Scalar
from src.blueprints.reconcile import Context, reconcile
from src.blueprints.spec import AgentSpec, WidgetKeySpec


class Thing(BaseModel):
    title: Annotated[str, Scalar(record="stored_title", says="rename to '{value}'")]
    note: Annotated[str | None, Scalar(record="note", omit_none=True)] = None
    tags: Annotated[list[str], Each(adds="tag {name}", removes="untag {name}")] = Field(default_factory=list)


@pytest.mark.parametrize("before_same, actual_same", list(product([True, False], repeat=2)))
def test_a_field_is_work_only_when_the_person_changed_it_and_it_isnt_already_so(before_same, actual_same):
    now = Thing(title="new")
    before = {"title": "new" if before_same else "old"}
    actual = {"title": "new" if actual_same else "elsewhere"}
    outcome = reconcile(now, actual, before)
    if before_same:
        # Not changed by the person: nothing to do, and a difference from actual is someone else's edit.
        assert outcome.sets == []
        assert [d.field for d in outcome.drift] == ([] if actual_same else ["title"])
    else:
        assert [s.field for s in outcome.sets] == ([] if actual_same else ["title"])
        assert outcome.drift == []


def test_without_memory_every_difference_is_work():
    outcome = reconcile(Thing(title="new"), {"title": "old"})
    assert [(s.field, s.value, s.says) for s in outcome.sets] == [("title", "new", "rename to 'new'")]
    assert outcome.values(Thing) == {"stored_title": "new"}


def test_a_missing_value_leaves_what_is_there():
    assert reconcile(Thing(title="t"), {"title": "t", "note": "kept"}).sets == []


@pytest.mark.parametrize(
    "before, now, actual, added, removed",
    [
        (None, ["a"], [], ["a"], []),          # added
        (None, ["a"], ["a", "b"], [], []),     # b was never declared: never touched
        (["a", "b"], ["a"], ["a", "b"], [], ["b"]),  # declared before, left out now: taken away
        (["a"], ["a"], ["a", "b"], [], []),    # b was added outside the blueprint: left alone
        (["a", "b"], ["a"], ["a"], [], []),    # already gone
    ],
)
def test_items_are_added_and_taken_away_by_key(before, now, actual, added, removed):
    outcome = reconcile(Thing(title="t", tags=now), {"title": "t", "tags": actual}, None if before is None else {
        "title": "t", "tags": before,
    })
    assert [item.key for item in outcome.added] == added
    assert [item.key for item in outcome.removed] == removed


def test_without_memory_nothing_is_taken_away():
    outcome = reconcile(Thing(title="t"), {"title": "t", "tags": ["a", "b"]})
    assert outcome.removed == []


def test_a_resource_being_deleted_isnt_also_disconnected():
    outcome = reconcile(
        Thing(title="t"), {"title": "t", "tags": ["b"]}, {"title": "t", "tags": ["b"]},
        ctx=Context(removing=frozenset({"b"})),
    )
    assert outcome.removed == []


def test_one_of_two_installs_can_be_taken_away_by_its_key():
    """With memory, an item left out goes by its own key, so one of two `send_email` installs can go."""
    def key(item):
        return f"{item['id']}:{item['to']}"

    class Agent(BaseModel):
        skills: Annotated[list[dict], Each(adds="add {name}", removes="remove {name}")] = Field(default_factory=list)

    sales, support = {"id": "send_email", "to": "sales"}, {"id": "send_email", "to": "support"}
    outcome = reconcile(Agent(skills=[sales]), {"skills": [sales, support]}, {"skills": [sales, support]},
                        Context(keys={"skills": key}))
    assert [item.key for item in outcome.removed] == ["send_email:support"]


def test_the_spec_declares_how_fields_change():
    agent = AgentSpec(kind="Agent", name="A", instructions="Be brief.", provider="OpenAI", model="gpt-5")
    outcome = reconcile(agent, {"name": "A", "instructions": "  Be brief.  ", "provider": "Bedrock"})
    # Provider and model are said once; trimmed instructions don't differ.
    assert outcome.says() == ("switch to OpenAI · gpt-5",)
    assert outcome.values(AgentSpec) == {"agent_provider": "OpenAI", "agent_model": "gpt-5"}

    widget = WidgetKeySpec(kind="WidgetKey", agent="a", allowed_origins=["https://B.example/page", "https://a.example"])
    same = {"allowed_origins": ["https://a.example", "https://b.example"], "allow_guests": False}
    assert reconcile(widget, same).sets == []
