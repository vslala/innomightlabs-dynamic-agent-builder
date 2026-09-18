from typing import cast

from src.dream.actions import DreamActionContext, DreamActionExecutor
from src.dream.models import DreamAction, DreamActionOutcome, DreamActionType
from src.memory.models import CoreMemory, MemoryBlockDefinition
from src.memory.repository import MemoryRepository


class FakeMemoryRepository:
    def __init__(self, lines: list[str] | None = None, known_blocks: set[str] | None = None) -> None:
        self.agent_id = "agent-1"
        self.user_id = "user-1"
        self.known_blocks = known_blocks if known_blocks is not None else {"human"}
        self.memories = {
            block_name: CoreMemory(
                agent_id=self.agent_id,
                user_id=self.user_id,
                block_name=block_name,
                lines=list(lines or []),
            )
            for block_name in self.known_blocks
        }
        self.saved: list[CoreMemory] = []
        self.archival: set[str] = set()

    def get_block_definition(self, agent_id: str, user_id: str, block_name: str):
        assert (agent_id, user_id) == (self.agent_id, self.user_id)
        if block_name not in self.known_blocks:
            return None
        return MemoryBlockDefinition(
            agent_id=agent_id, user_id=user_id, block_name=block_name, description="Test block"
        )

    def get_core_memory(self, agent_id: str, user_id: str, block_name: str):
        assert (agent_id, user_id) == (self.agent_id, self.user_id)
        return self.memories.get(block_name)

    def line_exists(self, agent_id: str, user_id: str, block_name: str, content: str):
        memory = self.memories.get(block_name)
        if memory is None or content not in memory.lines:
            return None
        return memory.lines.index(content) + 1

    def save_core_memory(self, memory: CoreMemory) -> None:
        self.memories[memory.block_name] = memory
        self.saved.append(memory.model_copy(deep=True))

    def insert_archival(self, agent_id: str, user_id: str, content: str):
        assert (agent_id, user_id) == (self.agent_id, self.user_id)
        is_new = content not in self.archival
        self.archival.add(content)
        return object(), is_new


def action(action_type: DreamActionType, **overrides: object) -> DreamAction:
    payload: dict[str, object] = {
        "type": action_type,
        "reason": "durable memory update",
        "confidence": 0.9,
        **overrides,
    }
    return DreamAction.model_validate(payload)


def execute(repository: FakeMemoryRepository, *actions: DreamAction):
    return DreamActionExecutor().execute(
        DreamActionContext(
            agent_id="agent-1",
            user_id="user-1",
            memory_repository=cast(MemoryRepository, repository),
        ),
        list(actions),
        min_confidence=0.75,
    )


def test_append_dedupes_existing_core_line() -> None:
    repository = FakeMemoryRepository(lines=["Prefers concise answers"])

    results = execute(repository, action(DreamActionType.APPEND_CORE, block_name="human", content="Prefers concise answers"))

    assert results[0][1:] == (DreamActionOutcome.SKIPPED_DUPLICATE, "core line already exists")
    assert repository.memories["human"].lines == ["Prefers concise answers"]
    assert repository.saved == []


def test_replace_and_delete_apply_in_descending_line_order() -> None:
    repository = FakeMemoryRepository(lines=["stale preference", "obsolete timezone", "keep this"])
    replace = action(DreamActionType.REPLACE_CORE, block_name="human", line_number=1, content="prefers detailed answers")
    delete = action(DreamActionType.DELETE_CORE, block_name="human", line_number=2)

    results = execute(repository, replace, delete)

    assert [result[1] for result in results] == [DreamActionOutcome.EXECUTED, DreamActionOutcome.EXECUTED]
    assert repository.memories["human"].lines == ["prefers detailed answers", "keep this"]


def test_replace_or_delete_with_stale_line_is_skipped() -> None:
    repository = FakeMemoryRepository(lines=["only line"])

    results = execute(repository, action(DreamActionType.REPLACE_CORE, block_name="human", line_number=2, content="new line"))

    assert results[0][1:] == (DreamActionOutcome.SKIPPED_STALE_LINE, "line number no longer exists")
    assert repository.memories["human"].lines == ["only line"]
    assert repository.saved == []


def test_core_action_for_unknown_block_is_skipped() -> None:
    repository = FakeMemoryRepository(known_blocks={"human"})

    results = execute(repository, action(DreamActionType.APPEND_CORE, block_name="persona", content="Helpful assistant"))

    assert results[0][1:] == (DreamActionOutcome.SKIPPED_UNKNOWN_BLOCK, "memory block does not exist")
    assert repository.saved == []


def test_archival_duplicate_is_not_inserted_twice() -> None:
    repository = FakeMemoryRepository()
    archival = action(DreamActionType.INSERT_ARCHIVAL, content="Long-term project context")

    results = execute(repository, archival, archival)

    assert [result[1] for result in results] == [DreamActionOutcome.EXECUTED, DreamActionOutcome.SKIPPED_DUPLICATE]
    assert repository.archival == {"Long-term project context"}


def test_secret_bearing_action_is_blocked_before_memory_mutation() -> None:
    repository = FakeMemoryRepository()

    results = execute(
        repository,
        action(DreamActionType.APPEND_CORE, block_name="human", content="password=super-secret"),
    )

    assert results[0][1:] == (DreamActionOutcome.SKIPPED_REDACTED, "content matched a secret pattern")
    assert repository.memories["human"].lines == []
    assert repository.saved == []
