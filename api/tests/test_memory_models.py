from src.memory.models import build_block_id


def test_build_block_id_is_deterministic():
    block_id = build_block_id("agent-1", "user-1", "human")
    assert block_id == "agent-1:user-1:human"
    assert block_id == build_block_id("agent-1", "user-1", "human")


def test_build_block_id_changes_with_inputs():
    base = build_block_id("agent-1", "user-1", "human")
    assert base != build_block_id("agent-2", "user-1", "human")
    assert base != build_block_id("agent-1", "user-2", "human")
    assert base != build_block_id("agent-1", "user-1", "persona")
