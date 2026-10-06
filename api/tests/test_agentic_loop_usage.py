"""Token usage recording forwards the turn's public API key, when there is one."""

from types import SimpleNamespace

import pytest

from src.agents.agentic_loop import _record_token_usage
from src.token_usage.models import TokenUsagePeriod, TokenUsageRecord
from src.skills.models import ActorKind


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def record_usage(self, **kwargs) -> TokenUsageRecord:
        self.calls.append(kwargs)
        return TokenUsageRecord(
            agent_id=kwargs["agent_id"],
            period=TokenUsagePeriod.DAY,
            period_key="2026-10-01",
            llm_model=kwargs["llm_model"],
        )


@pytest.mark.parametrize("api_key_id", ["key-1", None])
async def test_record_token_usage_forwards_api_key_id(api_key_id):
    from src.agents.runtime_state import AgentTurnState

    recorder = _Recorder()
    state = AgentTurnState(
        owner_email="owner@example.com",
        actor_email="owner@example.com",
        actor_id="secret-key:key-1",
        actor_kind=ActorKind.OWNER,
        conversation_id="conversation-1",
        agent_id="agent-1",
        model_name="model-a",
        user_message="Hi",
        api_key_id=api_key_id,
    )

    await _record_token_usage(recorder, state, SimpleNamespace(prompt_tokens=10, completion_tokens=5))

    assert recorder.calls[0]["api_key_id"] == api_key_id
    assert recorder.calls[0]["agent_id"] == "agent-1"
