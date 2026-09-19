"""Side-channel payloads carried in tool results.

These used to be a nested if/isinstance/.get pyramid inside the architecture's
event loop. See api/docs/LLD-agent-runtime-refactor.md (P1.8).
"""

import json

from src.agents.tool_results import interpret_tool_result
from src.llm.events import SSEEventType


def test_a_plain_text_result_contributes_nothing():
    assert interpret_tool_result("just some text") == []
    assert interpret_tool_result("") == []
    assert interpret_tool_result("{not json") == []
    assert interpret_tool_result(json.dumps(["a", "list"])) == []
    assert interpret_tool_result(json.dumps({"ok": True})) == []


def test_ui_form_render_becomes_its_own_event():
    [found] = interpret_tool_result(
        json.dumps(
            {
                "type": "ui_form_render",
                "form": {"form_name": "Lead capture", "form_id": "lead-1"},
                "submit_label": "Send",
            }
        )
    )

    assert found.event is not None
    assert found.event.event_type == SSEEventType.UI_FORM_RENDER
    assert found.event.content == "Lead capture"
    assert found.event.form_id == "lead-1"
    assert found.event.form_label == "Lead capture"
    assert found.event.submit_label == "Send"
    assert found.canvas is None


def test_a_form_without_identifiers_still_renders():
    [found] = interpret_tool_result(json.dumps({"type": "ui_form_render", "form": {}}))

    assert found.event is not None
    assert found.event.content == "Form"
    assert found.event.form_id is None
    assert found.event.form_label is None


def test_a_form_whose_fields_are_the_wrong_shape_is_ignored_not_crashed():
    [found] = interpret_tool_result(
        json.dumps({"type": "ui_form_render", "form": {"form_name": 7, "form_id": []}})
    )

    assert found.event is not None
    assert found.event.content == "Form"
    assert found.event.form_label is None
    assert found.event.form_id is None


def test_canvas_artifact_yields_an_event_and_something_to_attach():
    [found] = interpret_tool_result(
        json.dumps(
            {
                "type": "canvas_artifact",
                "ok": True,
                "artifact_id": "artifact-1",
                "title": "Revenue",
                "caption": "Q1",
                "mime_type": "text/html",
            }
        )
    )

    assert found.canvas is not None
    assert found.canvas.artifact_id == "artifact-1"
    assert found.canvas.title == "Revenue"
    assert found.event is not None
    assert found.event.event_type == SSEEventType.CANVAS_ARTIFACT_READY
    assert found.event.canvas_content_url.endswith("/artifacts/artifact-1/content")


def test_a_failed_canvas_artifact_is_not_attached():
    assert interpret_tool_result(
        json.dumps({"type": "canvas_artifact", "ok": False, "artifact_id": "artifact-1"})
    ) == []


def test_canvas_artifact_defaults_its_optional_metadata():
    [found] = interpret_tool_result(
        json.dumps({"type": "canvas_artifact", "ok": True, "artifact_id": "a1"})
    )

    assert found.canvas.title == "Canvas"
    assert found.canvas.mime_type == "text/html"
    assert found.canvas.caption is None


def test_auth_required_supplies_wording_but_no_event():
    [found] = interpret_tool_result(
        json.dumps(
            {
                "auth_required": True,
                "credential_setup_url": " https://example.com/setup ",
                "agent_name": "Billing Bot",
            }
        )
    )

    assert found.event is None
    assert found.fallback_text is not None
    assert found.fallback_text.startswith("Billing Bot requires credentials")
    assert "https://example.com/setup" in found.fallback_text


def test_auth_required_without_a_usable_url_contributes_nothing():
    for payload in (
        {"auth_required": True},
        {"auth_required": True, "credential_setup_url": "   "},
        {"auth_required": True, "credential_setup_url": 42},
        {"auth_required": False, "credential_setup_url": "https://example.com"},
    ):
        assert interpret_tool_result(json.dumps(payload)) == []


def test_auth_required_falls_back_to_a_generic_name():
    [found] = interpret_tool_result(
        json.dumps({"auth_required": True, "credential_setup_url": "https://example.com"})
    )

    assert found.fallback_text.startswith("the remote agent requires credentials")


def test_one_result_can_match_more_than_one_interpreter():
    found = interpret_tool_result(
        json.dumps(
            {
                "type": "canvas_artifact",
                "ok": True,
                "artifact_id": "a1",
                "auth_required": True,
                "credential_setup_url": "https://example.com",
            }
        )
    )

    assert len(found) == 2
    assert any(f.canvas is not None for f in found)
    assert any(f.fallback_text is not None for f in found)
