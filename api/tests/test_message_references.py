"""Message references: kinds attach, tag and recall what a message points at; the context shows the tags."""

import pytest

from src.llm.conversation_strategy import FixedWindowStrategy
from src.messages import references
from src.messages.models import Message, MessageReference
from src.messages.references import (
    ReferenceRefused,
    ReferenceRequest,
    attach_references,
    recall_line,
    reference_tags,
    references_by_kind,
)

CONVERSATION = object()


class Notes:
    kind = "note"

    def __init__(self):
        self.attached: list[list[str]] = []

    def attach(self, conversation, ids):
        self.attached.append(ids)
        return [MessageReference(kind=self.kind, id=i, label=f"note {i}") for i in ids]

    def describe(self, conversation, refs):
        return {ref.id: f'<attached_note id="{ref.id}">' for ref in refs if ref.id != "gone"}

    def recall_line(self, reference):
        return f"[note {reference.id}]"


@pytest.fixture
def notes(monkeypatch):
    kind = Notes()
    monkeypatch.setattr(references, "REFERENCE_KINDS", {"note": kind})
    return kind


def _message(*refs: MessageReference, content: str = "hello") -> Message:
    return Message(conversation_id="c", role="user", content=content, references=list(refs))


def test_references_are_attached_by_their_kind_each_id_once(notes):
    attached = attach_references(CONVERSATION, [ReferenceRequest(kind="note", id="1"), ReferenceRequest(kind="note", id="1")])

    assert [ref.id for ref in attached] == ["1"] and notes.attached == [["1"]]


def test_an_unknown_kind_is_refused_before_anything_is_attached(notes):
    with pytest.raises(ReferenceRefused) as refused:
        attach_references(CONVERSATION, [ReferenceRequest(kind="note", id="1"), ReferenceRequest(kind="video", id="2")])

    assert refused.value.code == "reference_kind_unknown" and notes.attached == []


def test_every_reference_in_the_conversation_is_found_once_by_kind():
    one, two = MessageReference(kind="note", id="1"), MessageReference(kind="note", id="2")

    found = references_by_kind([_message(one), _message(one, two), _message()])

    assert found == {"note": [one, two]}


def test_a_gone_target_or_an_unregistered_kind_still_reads_in_the_history(notes):
    tags = reference_tags(
        CONVERSATION,
        {"note": [MessageReference(kind="note", id="1"), MessageReference(kind="note", id="gone", label="old")],
         "video": [MessageReference(kind="video", id="v", label="clip")]},
    )

    assert tags[("note", "1")] == '<attached_note id="1">'
    assert "(no longer available)" in tags[("note", "gone")] and 'label="old"' in tags[("note", "gone")]
    assert "(no longer available)" in tags[("video", "v")]
    assert recall_line(MessageReference(kind="note", id="1")) == "[note 1]"
    assert recall_line(MessageReference(kind="video", id="v", label="clip")) == "[video v clip]"


def test_the_context_shows_each_reference_before_the_text_and_counts_it():
    ref = MessageReference(kind="note", id="1")
    tag = "<attached_note id=\"1\">\nfour more words here\n</attached_note>"
    messages = [_message(content="older message"), _message(ref, content="look at this")]

    context = FixedWindowStrategy(max_words=100).build_context(messages, reference_tags={("note", "1"): tag})
    tight = FixedWindowStrategy(max_words=5).build_context(messages, reference_tags={("note", "1"): tag})

    assert context[-1]["content"] == f"{tag}\n\nlook at this"
    assert tight == [], "the tag's words count against the budget"
