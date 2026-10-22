from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.skills.browser_studio import actions, client
from src.skills.browser_studio.client import BrowserStudioClient, endpoint_for
from src.skills.registry import SkillRegistry
from src.skills.workspaces import workspace_id_from_context

CONTEXT = {
    "owner_email": "owner@example.com",
    "actor_email": "actor@example.com",
    "agent_id": "agent_123",
    "installed_skill_id": "browser_studio",
    "conversation_id": "conv_123",
    "user_message_id": "msg_123",
}
ACTIONS = ["inspect_page", "record_walkthrough", "render_scene", "compose_video", "probe_media"]


@pytest.fixture(autouse=True)
def runner(monkeypatch) -> None:
    monkeypatch.setattr(client.settings, "cli_runner_base_url", "http://runner.local")
    monkeypatch.setattr(client.settings, "cli_runner_shared_token", "runner-token")
    monkeypatch.setattr(client.settings, "browser_studio_timeout_seconds", 330)


def studio(handler) -> BrowserStudioClient:  # type: ignore[no-untyped-def]
    return BrowserStudioClient(transport=httpx.MockTransport(handler))


def answering(status: int = 200, body: Any = None, **kwargs: Any):  # type: ignore[no-untyped-def]
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body if body is not None else {"ok": True}, **kwargs)

    handler.seen = seen  # type: ignore[attr-defined]
    return handler


def test_manifest_offers_the_five_actions_to_the_owner_only_and_not_to_automations() -> None:
    loaded = SkillRegistry(Path("src/skills")).get("browser_studio")

    assert loaded is not None
    assert [action.name for action in loaded.manifest.actions] == ACTIONS
    assert loaded.manifest.owner_only is True
    assert loaded.manifest.automation.enabled is False
    assert all(action.input_schema.get("additionalProperties") is False for action in loaded.manifest.actions)
    assert {a.name: a.input_schema["required"] for a in loaded.manifest.actions} == {
        "inspect_page": ["url"], "record_walkthrough": ["url"], "render_scene": ["output_path", "duration_seconds"],
        "compose_video": ["output", "clips"], "probe_media": ["path"],
    }


def test_the_schemas_an_agent_reads_stay_small() -> None:
    # The schemas of recently used actions go into every turn's prompt, so growth here is paid for on every turn.
    loaded = SkillRegistry(Path("src/skills")).get("browser_studio")

    assert loaded is not None
    size = sum(len(json.dumps(action.input_schema)) for action in loaded.manifest.actions)
    assert size <= 10_000, f"the action schemas came to {size} characters"
    assert len(loaded.manifest.system_prompt) <= 2_000


def test_the_agent_is_never_offered_the_identity_fields() -> None:
    loaded = SkillRegistry(Path("src/skills")).get("browser_studio")

    assert loaded is not None
    for action in loaded.manifest.actions:
        assert not {"workspace_id", "request_id"} & set(action.input_schema["properties"]), action.name


@pytest.mark.parametrize(
    "action, path",
    [
        ("inspect_page", "/v1/browser/inspections"),
        ("record_walkthrough", "/v1/browser/walkthroughs"),
        ("render_scene", "/v1/browser/scenes"),
        ("compose_video", "/v1/media/compositions"),
        ("probe_media", "/v1/media/probes"),
    ],
)
@pytest.mark.asyncio
async def test_each_action_goes_to_its_endpoint_with_the_workspace_and_the_token(action: str, path: str) -> None:
    handler = answering()

    result = await studio(handler).call(action, {"url": "https://example.com"}, CONTEXT)

    request = handler.seen[0]
    sent = json.loads(request.content)
    assert result == {"ok": True}
    assert (request.url.path, request.method) == (path, "POST")
    assert request.headers["authorization"] == "Bearer runner-token"
    assert sent["workspace_id"] == workspace_id_from_context(CONTEXT)
    assert sent["request_id"] == "msg_123"
    assert sent["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_an_agent_cannot_name_another_workspace() -> None:
    handler = answering()

    await studio(handler).call("inspect_page", {"url": "https://x.com", "workspace_id": "f" * 48, "request_id": "mine"}, CONTEXT)

    sent = json.loads(handler.seen[0].content)
    assert sent["workspace_id"] == workspace_id_from_context(CONTEXT)
    assert sent["request_id"] == "msg_123"


@pytest.mark.asyncio
async def test_a_run_without_a_conversation_has_no_workspace_and_never_reaches_the_runner() -> None:
    handler = answering()

    with pytest.raises(ValueError, match="conversation_id"):
        await studio(handler).call("inspect_page", {"url": "https://x.com"}, {"owner_email": "owner@example.com"})
    assert handler.seen == []


@pytest.mark.parametrize(
    "action, arguments, expected",
    [
        ("inspect_page", {}, 50),
        ("inspect_page", {"timeout_seconds": 40}, 65),
        ("record_walkthrough", {}, 165),
        ("record_walkthrough", {"max_duration_seconds": 180}, 225),
        ("render_scene", {"duration_seconds": 3}, 82.5),
        ("compose_video", {}, 315),
        ("probe_media", {}, 75),
        ("record_walkthrough", {"max_duration_seconds": "soon"}, 165),
        ("record_walkthrough", {"max_duration_seconds": True}, 165),
        ("record_walkthrough", {"max_duration_seconds": -5}, 165),
    ],
)
def test_each_job_is_waited_for_as_long_as_it_can_take(action: str, arguments: dict[str, Any], expected: float) -> None:
    assert endpoint_for(action).wait(arguments) == expected


@pytest.mark.asyncio
async def test_no_call_waits_longer_than_the_configured_ceiling(monkeypatch) -> None:
    monkeypatch.setattr(client.settings, "browser_studio_timeout_seconds", 100)
    waits: list[float] = []

    class Spy(httpx.AsyncClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            waits.append(kwargs["timeout"].read)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(client.httpx, "AsyncClient", Spy)
    await studio(answering()).call("compose_video", {}, CONTEXT)

    assert waits == [100]


@pytest.mark.parametrize(
    "status, body, expected",
    [
        (400, {"detail": "invalid_composition: clip 1 (clips/a.webm): start 50.0s is not before its end 5.80s"}, "start 50.0s is not before its end"),
        (400, {"detail": "not_found: clips/nope.webm doesn't exist in the workspace"}, "nope.webm doesn't exist"),
        (502, {"detail": "couldn't load the page: net::ERR_NAME_NOT_RESOLVED"}, "couldn't load the page"),
        (401, {"detail": "Invalid bearer token"}, "rejected this service's credentials"),
        (503, {"detail": "boom"}, "boom"),
    ],
)
@pytest.mark.asyncio
async def test_the_runners_own_words_reach_the_agent(status: int, body: dict, expected: str) -> None:
    with pytest.raises(RuntimeError, match="compose_video failed") as raised:
        await studio(answering(status, body)).call("compose_video", {}, CONTEXT)

    assert expected in str(raised.value)


@pytest.mark.asyncio
async def test_a_runner_that_predates_the_skill_is_named_as_the_problem() -> None:
    # What FastAPI answers for a route that doesn't exist: the agent saw only "Not Found" before.
    with pytest.raises(RuntimeError, match="older version") as raised:
        await studio(answering(404, {"detail": "Not Found"})).call("inspect_page", {"url": "https://x.com"}, CONTEXT)

    assert "inspect_page failed" in str(raised.value)
    assert "retrying won't help" in str(raised.value)


@pytest.mark.asyncio
async def test_a_rejected_field_is_reported_as_where_and_why() -> None:
    detail = [
        {"type": "value_error", "loc": ["body", "steps", 3, "target"], "msg": "Value error, a target needs exactly one of selector, role or text"},
        {"type": "literal_error", "loc": ["body", "clips", 1, "transition_in", "kind"], "msg": "Input should be 'fade' or 'dissolve'"},
    ]

    with pytest.raises(RuntimeError) as raised:
        await studio(answering(422, {"detail": detail})).call("record_walkthrough", {}, CONTEXT)

    assert "steps.3.target: a target needs exactly one of selector, role or text" in str(raised.value)
    assert "clips.1.transition_in.kind: Input should be 'fade' or 'dissolve'" in str(raised.value)
    assert "body." not in str(raised.value), "the transport detail is not the agent's concern"


@pytest.mark.asyncio
async def test_a_long_list_of_problems_is_cut_short() -> None:
    detail = [{"loc": ["body", "steps", n], "msg": f"bad {n}"} for n in range(20)]

    with pytest.raises(RuntimeError) as raised:
        await studio(answering(422, {"detail": detail})).call("record_walkthrough", {}, CONTEXT)

    assert "steps.4: bad 4" in str(raised.value)
    assert "steps.5" not in str(raised.value)
    assert "and 15 more" in str(raised.value)


@pytest.mark.asyncio
async def test_a_huge_error_body_is_bounded() -> None:
    with pytest.raises(RuntimeError) as raised:
        await studio(answering(500, {"detail": "x" * 5000})).call("compose_video", {}, CONTEXT)

    assert len(str(raised.value)) < 900


@pytest.mark.parametrize(
    "error, expected",
    [
        (httpx.ReadTimeout("slow"), "didn't finish within"),
        (httpx.ConnectError("no route"), "unreachable"),
        (httpx.RemoteProtocolError("hung up"), "RemoteProtocolError"),
    ],
)
@pytest.mark.asyncio
async def test_a_network_failure_says_what_to_do(error: Exception, expected: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    with pytest.raises(RuntimeError, match=expected):
        await studio(handler).call("record_walkthrough", {}, CONTEXT)


@pytest.mark.asyncio
async def test_a_reply_that_is_not_an_object_is_refused() -> None:
    for content in (b"<html>", b"[1, 2]", b'"text"'):
        def handler(request: httpx.Request, content: bytes = content) -> httpx.Response:
            return httpx.Response(200, content=content)

        with pytest.raises(RuntimeError, match="invalid response"):
            await studio(handler).call("probe_media", {}, CONTEXT)


@pytest.mark.asyncio
async def test_an_unconfigured_runner_is_reported_before_anything_is_sent(monkeypatch) -> None:
    handler = answering()
    monkeypatch.setattr(client.settings, "cli_runner_base_url", "")
    with pytest.raises(RuntimeError, match="CLI_RUNNER_BASE_URL"):
        await studio(handler).call("probe_media", {}, CONTEXT)
    monkeypatch.setattr(client.settings, "cli_runner_base_url", "http://runner.local")
    monkeypatch.setattr(client.settings, "cli_runner_shared_token", "")
    with pytest.raises(RuntimeError, match="CLI_RUNNER_SHARED_TOKEN"):
        await studio(handler).call("probe_media", {}, CONTEXT)
    assert handler.seen == []


def test_an_unknown_action_is_refused() -> None:
    with pytest.raises(ValueError, match="no action 'delete_everything'"):
        endpoint_for("delete_everything")


@pytest.mark.asyncio
async def test_the_runners_answer_is_returned_as_it_is_and_the_call_is_audited(monkeypatch, caplog) -> None:
    answer = {"status": "partial", "failure": {"index": 2, "error_code": "not_found"}, "steps": []}
    monkeypatch.setattr(actions, "get_browser_studio_client", lambda: studio(answering(200, answer)))

    with caplog.at_level(logging.INFO, logger=actions.__name__):
        result = await actions.record_walkthrough({"url": "https://example.com/pricing"}, {}, CONTEXT)

    assert result == answer
    audit = next(record.browser_studio_audit for record in caplog.records if hasattr(record, "browser_studio_audit"))
    assert audit["action"] == "record_walkthrough"
    assert audit["url"] == "https://example.com/pricing"
    assert audit["actor"] == "actor@example.com"
    assert audit["workspace"] == workspace_id_from_context(CONTEXT)
    assert audit["status"] == "partial"


@pytest.mark.asyncio
async def test_a_failed_call_is_audited_as_an_error(monkeypatch, caplog) -> None:
    monkeypatch.setattr(actions, "get_browser_studio_client", lambda: studio(answering(502, {"detail": "couldn't load the page"})))

    with caplog.at_level(logging.INFO, logger=actions.__name__), pytest.raises(RuntimeError):
        await actions.inspect_page({"url": "https://nowhere.invalid"}, {}, CONTEXT)

    assert next(r.browser_studio_audit for r in caplog.records if hasattr(r, "browser_studio_audit"))["status"] == "error"


@pytest.mark.asyncio
async def test_a_missing_context_is_reported_not_masked_by_the_audit(monkeypatch, caplog) -> None:
    monkeypatch.setattr(actions, "get_browser_studio_client", lambda: studio(answering()))

    with caplog.at_level(logging.INFO, logger=actions.__name__), pytest.raises(ValueError, match="conversation_id"):
        await actions.inspect_page({"url": "https://x.com"}, {}, {"owner_email": "owner@example.com"})


@pytest.mark.asyncio
async def test_arguments_must_be_an_object() -> None:
    with pytest.raises(ValueError, match="expected an object"):
        await actions.compose_video("not an object", {}, CONTEXT)  # type: ignore[arg-type]
