from datetime import datetime, timezone

from src.memory.models import CoreMemory, build_block_id


def test_build_block_id_is_deterministic():
    block_id = build_block_id("agent-1", "user-1", "human")
    assert block_id == "agent-1:user-1:human"
    assert block_id == build_block_id("agent-1", "user-1", "human")


def test_build_block_id_changes_with_inputs():
    base = build_block_id("agent-1", "user-1", "human")
    assert base != build_block_id("agent-2", "user-1", "human")
    assert base != build_block_id("agent-1", "user-2", "human")
    assert base != build_block_id("agent-1", "user-1", "persona")


def test_core_memory_to_dynamo_item_serializes_line_meta_datetimes():
    memory = CoreMemory(agent_id="agent-1", user_id="user-1", block_name="human")
    now = datetime.now(timezone.utc)
    memory.lines = ["user likes tea"]
    memory.ensure_line_meta(now=now)
    memory.line_meta[0].last_accessed_at = now

    item = memory.to_dynamo_item()

    assert isinstance(item["line_meta"][0]["created_at"], str)
    assert isinstance(item["line_meta"][0]["last_accessed_at"], str)
