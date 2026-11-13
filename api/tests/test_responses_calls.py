"""Function calls are assembled from a Responses stream whichever events carry their arguments, as vendors differ
(xAI's batch of four calls once arrived with no arguments we read). No call leaves the test."""

import json

import pytest

from src.llm.chat import read_tool_arguments
from src.llm.wire.responses import ResponseStream

LOAD_SOCIAL = '{"skill_id": "social_media"}'
LOAD_IMAGES = '{"skill_id": "image_generation"}'


def _item(index: int, *, arguments: str = "", item_id: str | None = None) -> dict:
    item = {"type": "function_call", "call_id": f"call-{index}", "name": "load_skill", "arguments": arguments}
    if item_id is not None:
        item["id"] = item_id
    return item


def added(index: int, item_id: str | None = "") -> dict:
    return {"type": "response.output_item.added", "output_index": index, "item": _item(index, item_id=item_id or f"fc-{index}")}


def delta(index: int, text: str) -> dict:
    return {"type": "response.function_call_arguments.delta", "item_id": f"fc-{index}", "output_index": index, "delta": text}


def arguments_done(index: int, arguments: str) -> dict:
    return {"type": "response.function_call_arguments.done", "item_id": f"fc-{index}", "output_index": index, "arguments": arguments}


def item_done(index: int, arguments: str = "") -> dict:
    return {"type": "response.output_item.done", "output_index": index, "item": _item(index, arguments=arguments, item_id=f"fc-{index}")}


def completed(*items: dict) -> dict:
    return {"type": "response.completed", "response": {"output": list(items), "usage": {"input_tokens": 1, "output_tokens": 1}}}


def calls(*events: dict) -> list[tuple[str, dict, str]]:
    stream = ResponseStream("Test")
    out = [event for raw in events for event in stream.read(raw)]
    return [(event.tool_use_id, event.tool_input, event.tool_input_error) for event in out if event.type == "tool_use"]


SOCIAL = ("call-0", {"skill_id": "social_media"}, "")
IMAGES = ("call-1", {"skill_id": "image_generation"}, "")


def test_arguments_streamed_as_deltas_are_joined():
    assert calls(added(0), delta(0, '{"skill_id": '), delta(0, '"social_media"}'), item_done(0), completed()) == [SOCIAL]


def test_a_batch_whose_arguments_come_only_in_their_done_events_keeps_every_call_s_own():
    assert calls(
        added(0), added(1), arguments_done(0, LOAD_SOCIAL), arguments_done(1, LOAD_IMAGES), item_done(0), item_done(1), completed()
    ) == [SOCIAL, IMAGES]


def test_arguments_only_on_the_finished_item_are_read():
    assert calls(added(0), added(1), item_done(0, LOAD_SOCIAL), item_done(1, LOAD_IMAGES), completed()) == [SOCIAL, IMAGES]


def test_a_vendor_that_never_closes_its_items_has_its_calls_read_from_the_completed_response():
    assert calls(added(0), added(1), completed(_item(0, arguments=LOAD_SOCIAL, item_id="fc-0"), _item(1, arguments=LOAD_IMAGES, item_id="fc-1"))) == [
        SOCIAL,
        IMAGES,
    ]


def test_calls_without_item_ids_are_matched_by_their_place_in_the_output():
    no_id = {"type": "response.output_item.added", "output_index": 0, "item": _item(0, item_id=None)}
    no_id_delta = {"type": "response.function_call_arguments.delta", "output_index": 0, "delta": LOAD_SOCIAL}

    assert calls(no_id, no_id_delta, completed()) == [SOCIAL]


def test_the_finished_item_wins_over_deltas_and_a_call_is_emitted_once():
    assert calls(
        added(0), delta(0, '{"skill_id": "soc'), item_done(0, LOAD_SOCIAL), completed(_item(0, arguments=LOAD_SOCIAL, item_id="fc-0"))
    ) == [SOCIAL]


def test_a_call_first_seen_finished_is_still_a_call():
    assert calls(item_done(0, LOAD_SOCIAL), completed()) == [SOCIAL]


def test_arguments_that_arent_a_json_object_say_why_instead_of_becoming_empty():
    [(_, tool_input, error)] = calls(added(0), delta(0, '{"skill_id": "soc'), completed())

    assert tool_input == {}
    assert "not valid JSON" in error and '{"skill_id": "soc' in error


def test_text_usage_and_the_stop_still_stream_around_the_calls():
    stream = ResponseStream("Test")
    raw = [{"type": "response.output_text.delta", "delta": "Loading."}, added(0), item_done(0, LOAD_SOCIAL), completed()]

    assert [event.type for event in (e for r in raw for e in stream.read(r))] == ["text", "tool_use", "usage", "stop"]


def test_a_failed_response_raises_with_its_error():
    with pytest.raises(RuntimeError, match="overloaded"):
        ResponseStream("Test").read({"type": "response.failed", "response": {"error": {"message": "overloaded"}}})


@pytest.mark.parametrize("arguments, expected", [
    (None, ({}, False)),
    ("", ({}, False)),
    ({"q": "x"}, ({"q": "x"}, False)),
    (json.dumps({"q": "x"}), ({"q": "x"}, False)),
    ("[1, 2]", ({}, True)),
    ("not json", ({}, True)),
    (42, ({}, True)),
])
def test_tool_arguments_are_an_object_or_nothing_and_anything_else_is_an_error(arguments, expected):
    tool_input, error = read_tool_arguments(arguments)

    assert (tool_input, bool(error)) == expected
