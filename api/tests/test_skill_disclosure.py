"""On-demand action disclosure, and keeping recently used action schemas in the prompt."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.agents.architectures.krishna_memgpt import KrishnaMemGPTArchitecture
from src.agents.agentic_loop import TurnComplete
from src.agents.models import Agent
from src.agents.tool_audit import build_tool_call_audit_message
from src.agents.tool_runtime.skill_contracts import LoadSkillInput
from src.conversations.models import Conversation
from src.llm.events import SSEEvent, SSEEventType
from src.memory.snapshot import CoreMemorySnapshot
from src.messages.models import Message, MessageKind
from src.messages.repositories.in_memory import InMemoryMessageRepository
from src.skills.disclosure import DisclosureRequest, disclose, search_actions, summarize
from src.skills.models import AgentSkill
from src.skills.registry import SkillRegistry
from src.skills.repository import AgentSkillRepository
from src.skills.service import SkillRuntimeService, SkillService
from src.skills.models import ActorKind

OWNER = "owner@example.com"

ON_DEMAND_MANIFEST = """
id: big_skill
namespace: test.big
name: Big Skill
description: A skill with many actions.
system_prompt: Always preview before applying.
action_disclosure: on_demand
actions:
  - name: list_campaigns
    group: campaigns
    description: List campaigns with their status. Use it to find campaign ids.
    input_schema: {type: object, properties: {limit: {type: integer}}}
    handler: actions:echo
  - name: pause_campaigns
    aliases: [pause_campaign]
    group: campaigns
    description: Pause campaigns so they stop spending.
    input_schema: {type: object, required: [campaign_ids], properties: {campaign_ids: {type: array}}}
    handler: actions:echo
  - name: add_negative_keywords
    group: keywords
    description: Add negative keywords to a campaign so ads stop showing for those searches.
    input_schema: {type: object, required: [keywords], properties: {keywords: {type: array}}}
    handler: actions:echo
  - name: get_search_terms
    group: reporting
    description: Search terms that triggered ads. Use it to find negative keyword candidates.
    input_schema: {type: object, properties: {}}
    handler: actions:echo
  - name: get_performance
    group: reporting
    description: Performance report by campaign.
    input_schema: {type: object, properties: {}}
    handler: actions:echo
  - name: list_keywords
    group: keywords
    description: List keywords.
    input_schema: {type: object, properties: {}}
    handler: actions:echo
"""

EAGER_MANIFEST = """
id: small_skill
namespace: test.small
name: Small Skill
description: A skill with one action.
actions:
  - name: search
    description: Search things.
    input_schema: {type: object, required: [query], properties: {query: {type: string}}}
    handler: actions:echo
"""


@pytest.fixture
def registry(tmp_path: Path) -> SkillRegistry:
    for folder, manifest in (("big_skill", ON_DEMAND_MANIFEST), ("small_skill", EAGER_MANIFEST)):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "manifest.yml").write_text(manifest)
    return SkillRegistry(root_dir=tmp_path)


def _manifest(registry: SkillRegistry, skill_id: str):
    loaded = registry.get(skill_id)
    assert loaded is not None
    return loaded.manifest


# --- disclosure --------------------------------------------------------------------------------


def test_eager_skill_discloses_every_schema(registry):
    disclosed = disclose(DisclosureRequest(manifest=_manifest(registry, "small_skill")))
    assert [action.name for action in disclosed.actions] == ["search"]
    assert disclosed.index is None


def test_on_demand_skill_discloses_an_index_without_schemas(registry):
    disclosed = disclose(DisclosureRequest(manifest=_manifest(registry, "big_skill")))
    assert disclosed.actions == []
    assert disclosed.index is not None
    assert list(disclosed.index) == ["campaigns", "keywords", "reporting"]
    assert disclosed.index["campaigns"][0] == ("list_campaigns", "List campaigns with their status.")


def test_named_actions_resolve_aliases_and_report_unknown_names(registry):
    disclosed = disclose(
        DisclosureRequest(manifest=_manifest(registry, "big_skill"), actions=["pause_campaign", "add_negatives"])
    )
    assert [action.name for action in disclosed.actions] == ["pause_campaigns"]
    assert disclosed.unknown == ["add_negatives"]
    assert disclosed.suggestions[0] == "add_negative_keywords"


def test_query_ranks_the_closest_action_first(registry):
    manifest = _manifest(registry, "big_skill")
    assert search_actions(manifest, "negative keywords", 5)[0].name == "add_negative_keywords"
    assert search_actions(manifest, "pause campaign", 5)[0].name == "pause_campaigns"
    assert [a.name for a in search_actions(manifest, "pause_campaign", 5)] == ["pause_campaigns"]
    assert search_actions(manifest, "zzz", 5) == []


def test_summary_is_the_first_sentence_capped():
    assert summarize("Pause campaigns. They stop spending.") == "Pause campaigns."
    long = summarize("x" * 200)
    assert len(long) == 90 and long.endswith("...")


def test_load_skill_input_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        LoadSkillInput.model_validate({"skill_id": "big_skill", "action": "list_campaigns"})


def test_google_ads_manifest_is_on_demand_with_short_summaries():
    manifest = _manifest(SkillRegistry(), "google_ads")
    disclosed = disclose(DisclosureRequest(manifest=manifest))
    assert disclosed.index is not None
    summaries = [summary for entries in disclosed.index.values() for _, summary in entries]
    assert len(summaries) == len(manifest.actions)
    assert all(not summary.endswith("...") for summary in summaries)


# --- runtime payload ---------------------------------------------------------------------------


def _runtime(registry: SkillRegistry, *skill_ids: str, agent_id: str = "agent-1") -> SkillRuntimeService:
    repository = AgentSkillRepository()
    for skill_id in skill_ids:
        manifest = _manifest(registry, skill_id)
        repository.save(
            AgentSkill(
                agent_id=agent_id,
                installed_skill_id=skill_id,
                skill_id=skill_id,
                namespace=manifest.namespace,
                skill_name=manifest.name,
                skill_description=manifest.description,
                installed_by=OWNER,
            )
        )
    return SkillRuntimeService(skill_service=SkillService(registry=registry, repository=repository), repository=repository)


def _load(runtime: SkillRuntimeService, **tool_input) -> dict:
    return json.loads(
        asyncio.run(
            runtime.handle_tool_call(
                tool_name="load_skill",
                tool_input=tool_input,
                agent_id="agent-1",
                owner_email=OWNER,
                actor_email=OWNER,
                actor_id=OWNER,
                actor_kind=ActorKind.OWNER,
                conversation_id="conversation-1",
            )
        )
    )


def test_load_skill_payloads_follow_the_disclosure_mode(registry, dynamodb_table):
    runtime = _runtime(registry, "big_skill", "small_skill")

    eager = _load(runtime, skill_id="small_skill")
    assert [action["name"] for action in eager["actions"]] == ["search"]
    assert eager["actions"][0]["schema"]["required"] == ["query"]
    assert "action_index" not in eager

    index = _load(runtime, skill_id="big_skill")
    assert "actions" not in index
    assert index["prompt"] == "Always preview before applying."
    assert index["action_index"]["keywords"][0]["name"] == "add_negative_keywords"

    named = _load(runtime, skill_id="big_skill", actions=["add_negative_keywords"])
    assert [action["name"] for action in named["actions"]] == ["add_negative_keywords"]
    assert named["actions"][0]["schema"]["required"] == ["keywords"]
    assert named["prompt"] == "Always preview before applying."

    searched = _load(runtime, skill_id="big_skill", query="search terms")
    assert searched["actions"][0]["name"] == "get_search_terms"


def test_execute_errors_carry_the_schema_or_suggestions(registry):
    with pytest.raises(ValueError, match=r"Missing required action argument: keywords\. Schema for 'add_negative_keywords'"):
        asyncio.run(registry.execute_action("big_skill", "add_negative_keywords", {}, {}, {}))
    with pytest.raises(ValueError, match="Did you mean: pause_campaigns"):
        asyncio.run(registry.execute_action("big_skill", "pause_campaign_now", {}, {}, {}))


# --- recent actions ----------------------------------------------------------------------------


def _audit_row(tool_name: str, tool_args: dict, *, success: bool = True) -> Message:
    from datetime import datetime, timezone

    audit = build_tool_call_audit_message(
        tool_call_id=f"call-{tool_name}",
        sequence=1,
        tool_name=tool_name,
        tool_args=tool_args,
        result="{}",
        success=success,
        started_at=datetime.now(timezone.utc),
    )
    return Message(
        conversation_id="conversation-1",
        created_by=OWNER,
        role="system",
        content=audit.model_dump_json(),
        kind=MessageKind.TOOL_AUDIT,
    )


def _executed(action: str, skill_id: str = "big_skill", **kwargs) -> Message:
    return _audit_row("execute_skill_action", {"skill_id": skill_id, "action": action, "arguments": {}}, **kwargs)


def test_recent_actions_keep_used_actions_newest_first_and_deduped(registry, dynamodb_table):
    runtime = _runtime(registry, "big_skill", "small_skill")
    enabled = runtime.list_enabled("agent-1")
    newest_first = [
        _executed("pause_campaign"),  # alias of pause_campaigns
        _executed("search", skill_id="small_skill"),
        _executed("pause_campaigns"),
        _audit_row("load_skill", {"skill_id": "big_skill", "actions": ["add_negative_keywords"]}),
        _executed("list_keywords", success=False),
        _executed("no_longer_exists"),
        _audit_row("search_docs", {"query": "x"}),
    ]

    recent = runtime.recent_actions(newest_first, enabled)

    assert [(skill.skill_id, [a.name for a in skill.actions]) for skill in recent] == [
        ("big_skill", ["pause_campaigns", "add_negative_keywords"]),
        ("small_skill", ["search"]),
    ]
    assert recent[0].prompt == "Always preview before applying."
    assert recent[0].actions[0].input_schema["required"] == ["campaign_ids"]


def test_recent_actions_are_capped(registry, dynamodb_table):
    runtime = _runtime(registry, "big_skill")
    names = ["list_campaigns", "pause_campaigns", "add_negative_keywords", "get_search_terms", "get_performance", "list_keywords"]
    recent = runtime.recent_actions([_executed(name) for name in names], runtime.list_enabled("agent-1"))
    assert [a.name for a in recent[0].actions] == names[: SkillRuntimeService.RECENT_ACTION_LIMIT]


def test_recent_actions_drop_disabled_skills(registry, dynamodb_table):
    runtime = _runtime(registry, "big_skill")
    assert runtime.recent_actions([_executed("pause_campaigns")], enabled_skills=[]) == []


class _FakeProviderSettingsRepository:
    def find_by_provider(self, owner_email, provider_name):
        class Settings:
            encrypted_credentials = "encrypted"

        return Settings()


async def _no_credentials(**kwargs):
    return {}


def test_turn_prompt_carries_the_schema_of_an_action_used_last_turn(registry, dynamodb_table, monkeypatch):
    prompts: list[str] = []
    turns = iter(
        [
            [
                SSEEvent(
                    event_type=SSEEventType.TOOL_CALL_START,
                    content="",
                    tool_call_id="t1",
                    tool_name="execute_skill_action",
                    tool_args={"skill_id": "big_skill", "action": "add_negative_keywords", "arguments": {"keywords": []}},
                ),
                SSEEvent(event_type=SSEEventType.TOOL_CALL_RESULT, content="{}", tool_call_id="t1", success=True),
                TurnComplete(full_text="Previewed."),
            ],
            [TurnComplete(full_text="Applied.")],
        ]
    )

    async def fake_loop(**kwargs):
        prompts.append(kwargs["context"][0]["content"])
        for item in next(turns):
            yield item

    monkeypatch.setattr("src.agents.architectures.krishna_memgpt.run_agentic_tool_loop", fake_loop)
    monkeypatch.setattr("src.agents.provider_session.get_llm_provider", lambda provider_name: object())
    monkeypatch.setattr("src.agents.provider_session.load_provider_credentials", _no_credentials)

    agent = Agent(
        agent_name="Ads Agent",
        agent_architecture="krishna-memgpt",
        agent_provider="Bedrock",
        agent_persona="Helpful",
        created_by=OWNER,
    )
    architecture = KrishnaMemGPTArchitecture(message_repository=InMemoryMessageRepository())
    architecture.provider_settings_repo = _FakeProviderSettingsRepository()
    architecture.skill_runtime = _runtime(registry, "big_skill", agent_id=agent.agent_id)
    architecture._get_linked_kb_ids = lambda agent_id, owner_email: []
    architecture._load_core_memory_snapshot = lambda agent_id, user_id: CoreMemorySnapshot(block_defs=[], blocks={})
    conversation = Conversation(title="Ads", agent_id=agent.agent_id, created_by=OWNER)

    async def turn(text: str) -> None:
        async for _ in architecture.handle_message(
            agent=agent,
            conversation=conversation,
            user_message=text,
            owner_email=OWNER,
            actor_email=OWNER,
            actor_id=OWNER,
            actor_kind=ActorKind.OWNER,
            attachments=[],
        ):
            pass

    asyncio.run(turn("Exclude free searches"))
    asyncio.run(turn("Yes, apply it"))

    first, second = prompts
    assert "<loaded_skill" not in first
    assert '<loaded_skill id="big_skill">' in second
    assert "- add_negative_keywords: Add negative keywords" in second
    assert '"required": ["keywords"]' in second
    # Only the used action, not the whole on-demand skill.
    assert "pause_campaigns" not in second
