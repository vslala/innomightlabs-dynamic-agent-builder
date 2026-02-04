from datetime import datetime, timezone, timedelta


def _mk_block_def(agent_id: str, user_id: str, name: str, limit: int, policy: str):
    from src.memory.models import MemoryBlockDefinition

    return MemoryBlockDefinition(
        agent_id=agent_id,
        user_id=user_id,
        block_name=name,
        description="test",
        word_limit=limit,
        eviction_policy=policy,
        is_default=False,
    )


def test_lru_eviction_removes_least_recently_accessed(dynamodb_table):
    from src.memory.models import CoreMemory
    from src.memory.eviction import MemoryEvictionService
    from src.memory.repository import MemoryRepository

    agent_id = "agent-1"
    user_id = "user-1"
    block_name = "projects"

    repo = MemoryRepository()
    block_def = _mk_block_def(agent_id, user_id, block_name, limit=6, policy="lru")
    repo.save_block_definition(block_def)

    mem = CoreMemory(agent_id=agent_id, user_id=user_id, block_name=block_name)
    mem.lines = ["one two", "three four", "five six"]  # 2 words each => 6 total
    now = datetime.now(timezone.utc)
    mem.ensure_line_meta(now=now)

    # mark access times: line0 oldest, line1 newest, line2 middle
    mem.line_meta[0].last_accessed_at = now - timedelta(minutes=10)
    mem.line_meta[1].last_accessed_at = now - timedelta(minutes=1)
    mem.line_meta[2].last_accessed_at = now - timedelta(minutes=5)

    # append another 2-word line => overflow to 8 words -> should evict line0 (oldest access)
    mem.lines.append("seven eight")
    mem.ensure_line_meta(now=now)
    mem.line_meta[-1].last_accessed_at = now

    svc = MemoryEvictionService()
    res = svc.apply_if_needed(mem, block_def, now=now)

    assert res.evicted_count == 1
    assert "one two" in res.evicted_lines
    assert mem.compute_word_count() <= block_def.word_limit


def test_fifo_eviction_removes_oldest_inserted(dynamodb_table):
    from src.memory.models import CoreMemory
    from src.memory.eviction import MemoryEvictionService
    from src.memory.repository import MemoryRepository

    agent_id = "agent-1"
    user_id = "user-1"
    block_name = "projects"

    repo = MemoryRepository()
    block_def = _mk_block_def(agent_id, user_id, block_name, limit=4, policy="fifo")
    repo.save_block_definition(block_def)

    mem = CoreMemory(agent_id=agent_id, user_id=user_id, block_name=block_name)
    mem.lines = ["one two", "three four"]  # 4 words total
    now = datetime.now(timezone.utc)
    mem.ensure_line_meta(now=now)

    # overflow by appending another 2 words
    mem.lines.append("five six")
    mem.ensure_line_meta(now=now)

    svc = MemoryEvictionService()
    res = svc.apply_if_needed(mem, block_def, now=now)

    assert res.evicted_count == 1
    assert res.evicted_lines[0] == "one two"  # first in
    assert mem.compute_word_count() <= block_def.word_limit
