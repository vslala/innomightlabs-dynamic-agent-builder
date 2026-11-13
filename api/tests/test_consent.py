"""Action consent: the gate, the request's lifecycle, the paused turn, and running what the person approved.

See docs/LLD-action-consent.md.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.agents.agentic_loop import POST_TOOL_CONTINUATION_PROMPT, TurnPaused, run_agentic_tool_loop
from src.agents.models import Agent
from src.agents.runtime_state import AgentTurnState
from src.agents.tool_execution import ToolExecutionRouter
from src.agents.tool_runtime import ToolExecutionOutcome, build_default_tool_registry
from src.agents.tool_runtime.specs import ToolCategory
from src.consent.continuation import ConsentContinuation, decision_line
from src.consent.gate import ConsentGate, SkillActions
from src.consent.models import ConsentRequest, ConsentScope, ConsentStatus, SkillActionSubject, StandingConsent, TurnCheckpoint, skill_key
from src.consent.payloads import is_consent_request
from src.consent.preview import ConsentPreview, TextBlock
from src.consent.repository import ConsentRepository, ConsentStateChanged
from src.messages.models import Message
from src.messages.repositories.in_memory import InMemoryMessageRepository
from src.skills.models import ActorKind, AgentSkill, SkillActionManifest
from src.skills.registry import ConsentMissingError, SkillRegistry
from src.skills.repository import AgentSkillRepository
from src.skills.service import SkillRuntimeService, SkillService
from tests.mock_data import account_for, agent_fields, owner_for, user_id_for

OWNER = "owner@example.com"
AGENT_ID = "agent-1"
CONVERSATION_ID = "conversation-1"

POSTER_MANIFEST = """
id: poster
namespace: test.poster
name: Poster
description: Posts things.
actions:
  - name: post
    description: Post the text.
    consent:
      title: Post it
      warning: Public.
      editable: [text]
      preview: actions:post_preview
    input_schema: {type: object, required: [text], properties: {text: {type: string}, tags: {type: array}}}
    handler: actions:post
  - name: look
    description: Look around.
    input_schema: {type: object, properties: {}}
    handler: actions:look
"""


@pytest.fixture
def posted(tmp_path: Path, monkeypatch) -> list[dict[str, Any]]:
    """What the poster skill's handlers were called with; its module is real, only not on disk."""
    calls: list[dict[str, Any]] = []
    module = types.ModuleType("src.skills.poster.actions")

    async def post(arguments, config, context):
        calls.append({"arguments": arguments, "context": context})
        return {"posted": arguments["text"]}

    async def look(arguments, config, context):
        return "looked"

    async def post_preview(arguments, config, context):
        return {"blocks": [TextBlock(label="Post", value=arguments["text"], argument="text").model_dump()]}

    module.post, module.look, module.post_preview = post, look, post_preview
    monkeypatch.setitem(sys.modules, "src.skills.poster.actions", module)
    (tmp_path / "poster").mkdir()
    (tmp_path / "poster" / "manifest.yml").write_text(POSTER_MANIFEST)
    return calls


@pytest.fixture
def runtime(tmp_path: Path, posted, dynamodb_table) -> SkillRuntimeService:
    registry = SkillRegistry(root_dir=tmp_path)
    repository = AgentSkillRepository()
    repository.save(
        AgentSkill(
            agent_id=AGENT_ID, installed_skill_id="poster", skill_id="poster", namespace="test.poster",
            skill_name="Poster", skill_description="Posts things.", installed_by=OWNER,
            # Shared with members, so it is the consent rule, not the install, that keeps them out
            available_to=[ActorKind.OWNER, ActorKind.MEMBER],
        )
    )
    return SkillRuntimeService(skill_service=SkillService(registry=registry, repository=repository), repository=repository)


class _NoNativeTools:
    async def execute(self, tool_name, tool_input, context):
        raise AssertionError("no native tool should run")


def _state(actor_kind: ActorKind = ActorKind.OWNER, scope: ConsentScope | None = None) -> AgentTurnState:
    return AgentTurnState(
        owner_email=OWNER, actor_email=OWNER, actor_id=OWNER, actor_kind=actor_kind,
        conversation_id=CONVERSATION_ID, agent_id=AGENT_ID, model_name="model-1", user_message="post hello",
        account_id=account_for(OWNER), owner_id=user_id_for(OWNER), consent_scope=scope or ConsentScope.interactive(),
    )


def _router(runtime: SkillRuntimeService) -> ToolExecutionRouter:
    registry = build_default_tool_registry(skill_runtime=runtime, native_tools=_NoNativeTools())
    return ToolExecutionRouter(registry, offered={ToolCategory.SKILL}, consent=ConsentGate([SkillActions(runtime)]))


def _post(router: ToolExecutionRouter, state: AgentTurnState, *, action: str = "post", text: str = "hello") -> ToolExecutionOutcome:
    return asyncio.run(
        router.execute(
            tool_name="execute_skill_action",
            tool_input={"skill_id": "poster", "action": action, "arguments": {"text": text}},
            tool_use_id="tooluse-1",
            state=state,
        )
    )


# --- the registry's invariant and the manifest contract ----------------------------------------


def test_a_consent_action_never_runs_without_a_recorded_grant(runtime, posted):
    registry = runtime.skill_service.registry
    run = lambda context: asyncio.run(registry.execute_action("poster", "post", {"text": "hi"}, {}, context))  # noqa: E731
    with pytest.raises(ConsentMissingError):
        run({})
    assert posted == []
    run({"consent_grant": "consent:consent_1"})
    assert len(posted) == 1


def test_consent_editable_must_name_the_actions_arguments():
    with pytest.raises(ValidationError, match="doesn't have"):
        SkillActionManifest.model_validate({
            "name": "post", "description": "Post.", "handler": "actions:post",
            "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}},
            "consent": {"title": "Post it", "editable": ["body"]},
        })


def test_the_real_skills_that_act_for_the_person_ask_first():
    registry = SkillRegistry()
    asking = {
        (skill.manifest.id, action.name)
        for skill in registry.list()
        for action in skill.manifest.actions
        if action.consent
    }
    assert {("social_media", "publish"), ("google_mail", "send"), ("google_mail", "send_draft")} <= asking


# --- the gate ----------------------------------------------------------------------------------


def test_the_owner_is_shown_a_card_and_nothing_runs(runtime, posted):
    outcome = _post(_router(runtime), _state())

    assert outcome.ends_turn and outcome.success and is_consent_request(outcome.result)
    assert posted == []
    card = json.loads(outcome.result)["consent"]
    assert card["title"] == "Post it" and card["state"] == "pending"
    assert card["editable"] == ["text"]
    # The skill's preview, then the manifest's warning
    assert [block["kind"] for block in card["blocks"]] == ["text", "warning"]
    stored = ConsentRepository().get(card["consent_id"])
    assert stored is not None and stored.arguments == {"text": "hello"} and stored.tool_use_id == "tooluse-1"


def test_a_call_that_needs_no_consent_runs_as_before(runtime):
    outcome = _post(_router(runtime), _state(), action="look")
    assert outcome.result == "looked" and not outcome.ends_turn


def test_nobody_but_the_owner_can_make_a_consent_action_run(runtime, posted):
    outcome = _post(_router(runtime), _state(ActorKind.MEMBER))
    assert not outcome.success and not outcome.ends_turn
    assert json.loads(outcome.result)["consent"] == "refused"
    assert posted == []


def test_always_allowed_runs_without_a_card_in_chat_and_unattended(runtime, posted):
    key = skill_key("poster", "post")
    ConsentRepository().save_standing(StandingConsent(agent_id=AGENT_ID, key=key, title="Post it", granted_by="u"))

    for scope in (ConsentScope.interactive(), ConsentScope.unattended()):
        outcome = _post(_router(runtime), _state(scope=scope))
        assert not outcome.ends_turn and json.loads(outcome.result) == {"posted": "hello"}
    assert [call["context"]["consent_grant"] for call in posted] == [f"standing:{AGENT_ID}/{key}"] * 2


def test_unattended_without_consent_is_refused_and_an_automation_step_grant_runs(runtime, posted):
    refused = _post(_router(runtime), _state(scope=ConsentScope.unattended()))
    assert json.loads(refused.result)["consent"] == "refused" and posted == []

    scope = ConsentScope.automation_step([skill_key("poster", "post")], "automation:auto-1/node-1")
    ran = _post(_router(runtime), _state(scope=scope))
    assert json.loads(ran.result) == {"posted": "hello"}
    assert posted[0]["context"]["consent_grant"] == "automation:auto-1/node-1"


def test_non_owners_are_never_told_about_consent_actions(runtime):
    def actions_for(actor_kind):
        payload = asyncio.run(runtime.handle_tool_call(
            tool_name="load_skill", tool_input={"skill_id": "poster"}, agent_id=AGENT_ID,
            account_id=account_for(OWNER), owner_id=user_id_for(OWNER), owner_email=OWNER,
            actor_email=OWNER, actor_id=OWNER, actor_kind=actor_kind, conversation_id=CONVERSATION_ID,
        ))
        return {action["name"]: action.get("asks_for_approval", False) for action in json.loads(payload)["actions"]}

    assert actions_for(ActorKind.OWNER) == {"post": True, "look": False}
    assert actions_for(ActorKind.MEMBER) == {"look": False}


# --- the request ---------------------------------------------------------------------------------


def _request(**changes) -> ConsentRequest:
    fields: dict[str, Any] = dict(
        conversation_id=CONVERSATION_ID, agent_id=AGENT_ID, account_id=account_for(OWNER), owner_id=user_id_for(OWNER),
        owner_email=OWNER, actor_email=OWNER, actor_id=OWNER, tool_use_id="tooluse-1",
        subject=SkillActionSubject(skill_id="poster", installed_skill_id="poster", action="post"),
        key=skill_key("poster", "post"), title="Post it", arguments={"text": "hello", "tags": ["a"]},
        preview=ConsentPreview(title="Post it"), editable=["text", "tags"],
    )
    return ConsentRequest(**{**fields, **changes})


def test_a_card_is_decided_once(dynamodb_table):
    repository = ConsentRepository()
    request = repository.open(_request())
    repository.decide(request, approve=True, by="u")
    with pytest.raises(ConsentStateChanged):
        repository.decide(request, approve=False, by="u")
    assert repository.get(request.consent_id).status is ConsentStatus.APPROVED


def test_a_new_card_for_the_same_action_replaces_the_pending_one(dynamodb_table):
    repository = ConsentRepository()
    first = repository.open(_request())
    other = repository.open(_request(key="skill:poster.other"))
    repository.open(_request())
    assert repository.get(first.consent_id).status is ConsentStatus.SUPERSEDED
    assert repository.get(other.consent_id).status is ConsentStatus.PENDING


def test_edits_must_be_editable_and_keep_the_arguments_kind():
    request = _request()
    assert request.checked_edits({"text": "bye", "tags": ["b"]}) == {"text": "bye", "tags": ["b"]}
    for edits in ({"other": "x"}, {"text": 3}, {"tags": "b"}):
        with pytest.raises(ValueError):
            request.checked_edits(edits)


def test_a_card_left_too_long_expires_and_a_call_that_died_running_is_unknown():
    old = datetime.now(timezone.utc) - timedelta(days=2)
    assert _request(created_at=old).state() == "expired" and not _request(created_at=old).is_open()
    assert _request(status=ConsentStatus.RUNNING, started_at=old).state() == "unknown"


def test_a_big_checkpoint_goes_to_s3_and_keeps_its_thought_signatures(dynamodb_table):
    import boto3
    from src.config import settings

    boto3.client("s3", region_name=settings.conversation_media_region).create_bucket(Bucket=settings.conversation_media_bucket)
    repository = ConsentRepository()
    request = repository.open(_request())
    exchange = [{"role": "assistant", "content": [{"toolUse": {"toolUseId": "t", "name": "x", "input": {}, "thoughtSignature": b"\x00sig"}}]},
                {"role": "user", "content": [{"text": "x" * 250_000}]}]
    kept = repository.keep_checkpoint(request, TurnCheckpoint(tool_use_id="t", model_name="m", exchange=exchange))
    assert kept.checkpoint.exchange is None and kept.checkpoint.exchange_ref
    assert repository.exchange_of(repository.get(request.consent_id).checkpoint) == exchange


# --- the paused turn -----------------------------------------------------------------------------


class _ToolCall:
    def __init__(self, tool_use_id: str, name: str):
        self.type, self.content, self.tool_name, self.tool_use_id = "tool_use", "", name, tool_use_id
        self.tool_input: dict[str, Any] = {}
        self.thought_signature = b"sig-" + tool_use_id.encode()


class _Event:
    def __init__(self, type: str, content: str = ""):
        self.type, self.content = type, content


class _Provider:
    """First call: some text and two tool calls. Any later call: an answer."""

    def __init__(self):
        self.contexts: list[list[dict]] = []

    async def stream_response(self, context, credentials, tools, model, cache_key=None):
        self.contexts.append(json.loads(json.dumps(context, default=str)))
        if len(self.contexts) == 1:
            yield _Event("text", "Here it is. ")
            yield _ToolCall("ask", "needs_consent")
            yield _ToolCall("later", "something_else")
        else:
            yield _Event("text", "Posted.")
        yield _Event("stop")


class _Router:
    def __init__(self):
        self.ran: list[str] = []

    async def execute(self, *, tool_name, tool_input, tool_use_id, state):
        self.ran.append(tool_name)
        return ToolExecutionOutcome(result='{"type": "consent_request"}', success=True, ends_turn=True)


class _NoUsage:
    def record_usage(self, **kwargs):
        return None


def _loop(provider, router, context, **kwargs) -> list:
    async def collect():
        return [item async for item in run_agentic_tool_loop(
            provider=provider, context=context, credentials={}, tools=[], model="m", tool_router=router,
            state=_state(), token_usage_service=_NoUsage(), **kwargs,
        )]
    return asyncio.run(collect())


def test_a_turn_pauses_on_a_card_and_skips_what_came_after_it():
    provider, router = _Provider(), _Router()
    context = [{"role": "system", "content": "s"}, {"role": "user", "content": "post hello"}]
    items = _loop(provider, router, context)

    assert router.ran == ["needs_consent"] and len(provider.contexts) == 1
    paused = next(item for item in items if isinstance(item, TurnPaused))
    assert paused.tool_use_id == "ask"
    assistant, results = paused.exchange
    assert assistant["content"][0] == {"text": "Here it is. "}
    assert assistant["content"][1]["toolUse"]["thoughtSignature"] == b"sig-ask"
    skipped = json.loads(results["content"][1]["toolResult"]["content"][0]["text"])
    assert "waiting for the person" in skipped["skipped"]
    # No instruction rides on the exchange: a resumed turn adds its own
    assert all("toolResult" in block for block in results["content"])


def test_a_resumed_turn_carries_on_from_its_exchange():
    provider = _Provider()
    provider.contexts.append([])  # so this provider answers straight away
    exchange = [{"role": "assistant", "content": [{"toolUse": {"toolUseId": "ask", "name": "x", "input": {}}}]},
                {"role": "user", "content": [{"toolResult": {"toolUseId": "ask", "content": [{"text": '{"consent": "approved"}'}]}}]}]
    context = [{"role": "system", "content": "s"}, {"role": "user", "content": "post hello"}]
    _loop(provider, _Router(), context, resume_exchange=exchange)

    seen = provider.contexts[1]
    tool_use, results = exchange
    assert seen[2] == tool_use
    # The decision as the call's result, then the instruction to carry on
    assert seen[3]["content"] == [*results["content"], {"text": POST_TOOL_CONTINUATION_PROMPT}]


# --- running what was approved --------------------------------------------------------------------


def _agent(model: str = "model-1") -> Agent:
    return Agent(agent_name="A", agent_architecture="krishna-memgpt", agent_provider="Bedrock", agent_persona="p",
                 agent_model=model, agent_id=AGENT_ID, **agent_fields(OWNER))


def _paused_request(repository: ConsentRepository, messages: InMemoryMessageRepository) -> ConsentRequest:
    request = repository.open(_request(arguments={"text": "hello"}, editable=["text"]))
    reply = Message(conversation_id=CONVERSATION_ID, role="assistant", content="Please review this.")
    messages.save(reply)
    exchange = [{"role": "assistant", "content": [{"toolUse": {"toolUseId": "tooluse-1", "name": "execute_skill_action", "input": {}}}]},
                {"role": "user", "content": [{"toolResult": {"toolUseId": "tooluse-1", "content": [{"text": "{}"}]}}]}]
    return repository.keep_checkpoint(
        request, TurnCheckpoint(tool_use_id="tooluse-1", model_name="model-1", exchange=exchange, assistant_message_id=reply.message_id)
    )


def _continue(runtime, repository, messages, request, agent=None):
    events: list = []
    continuation = ConsentContinuation(request.consent_id, agent or _agent(), repository=repository,
                                       message_repo=messages, skill_runtime=runtime)
    return asyncio.run(continuation.run(events.append)), events


def test_approving_runs_the_stored_call_with_the_edits_and_resumes_the_turn(runtime, posted):
    repository, messages = ConsentRepository(), InMemoryMessageRepository()
    request = repository.decide(_paused_request(repository, messages), approve=True, by="u", edits={"text": "bye"})

    turn_input, events = _continue(runtime, repository, messages, request)

    assert posted[0]["arguments"] == {"text": "bye"}
    assert posted[0]["context"]["consent_grant"] == f"consent:{request.consent_id}"
    assert repository.get(request.consent_id).status is ConsentStatus.SUCCEEDED
    assert [e.event_type.value for e in events] == ["TOOL_CALL_START", "TOOL_CALL_RESULT", "CONSENT_UPDATED"]
    assert turn_input.resume is not None
    answered = json.loads(turn_input.resume.exchange[1]["content"][0]["toolResult"]["content"][0]["text"])
    assert answered["consent"] == "approved" and answered["edited"] == ["text"] and answered["result"] == {"posted": "bye"}
    assert 'decision="approved"' in turn_input.user_message and 'edited="text"' in turn_input.user_message


def test_rejecting_runs_nothing_and_tells_the_turn_why(runtime, posted):
    repository, messages = ConsentRepository(), InMemoryMessageRepository()
    request = repository.decide(_paused_request(repository, messages), approve=False, by="u", reason="Too long")

    turn_input, _ = _continue(runtime, repository, messages, request)

    assert posted == []
    answered = json.loads(turn_input.resume.exchange[1]["content"][0]["toolResult"]["content"][0]["text"])
    assert answered == {"consent": "rejected", "reason": "Too long"}


def test_a_turn_is_not_resumed_once_the_conversation_moved_on_or_the_model_changed(runtime, posted):
    repository, messages = ConsentRepository(), InMemoryMessageRepository()
    request = repository.decide(_paused_request(repository, messages), approve=False, by="u")
    assert _continue(runtime, repository, messages, request, agent=_agent("model-2"))[0].resume is None

    messages.save(Message(conversation_id=CONVERSATION_ID, role="user", content="Actually, wait"))
    turn_input, _ = _continue(runtime, repository, messages, request)
    assert turn_input.resume is None
    assert turn_input.user_message == decision_line(request)


def test_a_handler_that_raises_ends_the_request_failed(runtime, posted, monkeypatch):
    async def broken(arguments, config, context):
        raise RuntimeError("network down")

    monkeypatch.setattr(sys.modules["src.skills.poster.actions"], "post", broken)
    repository, messages = ConsentRepository(), InMemoryMessageRepository()
    request = repository.decide(_paused_request(repository, messages), approve=True, by="u")
    turn_input, _ = _continue(runtime, repository, messages, request)
    assert repository.get(request.consent_id).status is ConsentStatus.FAILED
    assert "It failed" in turn_input.user_message


def test_uninstalling_a_skill_drops_what_was_always_allowed_for_it(runtime):
    repository = ConsentRepository()
    for key in (skill_key("poster", "post"), skill_key("other", "post")):
        repository.save_standing(StandingConsent(agent_id=AGENT_ID, key=key, title="Post it", granted_by="u"))
    runtime.skill_service.uninstall(agent_id=AGENT_ID, installed_skill_id="poster", owner=owner_for(OWNER))
    assert [consent.key for consent in repository.list_standing(AGENT_ID)] == [skill_key("other", "post")]
