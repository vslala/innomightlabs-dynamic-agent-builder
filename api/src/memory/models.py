"""
Memory models for the memGPT architecture.

Includes:
- MemoryBlockDefinition: Defines available memory blocks per agent
- CoreMemory: In-context memory loaded every turn
- ArchivalMemory: Long-term searchable memory
"""

import hashlib
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from enum import Enum

from pydantic import BaseModel, Field


def build_block_id(agent_id: str, user_id: str, block_name: str) -> str:
    return f"{agent_id}:{user_id}:{block_name}"


class EvictionPolicy(str, Enum):
    NONE = "none"
    LRU = "lru"
    FIFO = "fifo"
    # Future: COMPACT = "compact"


class MemoryBlockDefinition(BaseModel):
    """
    Defines a memory block available to an agent.

    Default blocks are "human" and "persona".
    Users can create custom blocks with configurable word limits.
    """
    agent_id: str
    user_id: str
    block_id: str = ""
    block_name: str
    description: str
    word_limit: int = 5000
    # Overflow handling policy for this block (strategy pattern)
    eviction_policy: EvictionPolicy = EvictionPolicy.NONE
    is_default: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def __init__(self, **data):
        super().__init__(**data)
        if not self.block_id:
            self.block_id = build_block_id(self.agent_id, self.user_id, self.block_name)

    @property
    def pk(self) -> str:
        return f"Agent#{self.agent_id}#User#{self.user_id}"

    @property
    def sk(self) -> str:
        return f"MemoryBlockDef#{self.block_id}"

    def to_dynamo_item(self) -> dict:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "block_id": self.block_id,
            "block_name": self.block_name,
            "description": self.description,
            "word_limit": self.word_limit,
            "eviction_policy": self.eviction_policy.value,
            "is_default": self.is_default,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dynamo_item(cls, item: dict) -> "MemoryBlockDefinition":
        return cls(
            agent_id=item["agent_id"],
            user_id=item["user_id"],
            block_id=item.get("block_id")
            or build_block_id(item["agent_id"], item["user_id"], item["block_name"]),
            block_name=item["block_name"],
            description=item["description"],
            word_limit=item.get("word_limit", 5000),
            eviction_policy=EvictionPolicy(item.get("eviction_policy", "none")),
            is_default=item.get("is_default", False),
            created_at=datetime.fromisoformat(item["created_at"]),
        )


class CoreMemoryLineMeta(BaseModel):
    """Per-line metadata for core memory to support eviction policies (LRU/FIFO)."""

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed_at: Optional[datetime] = None


class CoreMemory(BaseModel):
    """
    In-context memory that is loaded into the system prompt every turn.

    Stores content as a list of lines for line-based editing.
    Tracks word count for capacity management.
    """
    agent_id: str
    user_id: str
    block_id: str = ""
    block_name: str
    lines: list[str] = Field(default_factory=list)
    # Metadata aligned by index with `lines`
    line_meta: list[CoreMemoryLineMeta] = Field(default_factory=list)
    word_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    def __init__(self, **data):
        super().__init__(**data)
        if not self.block_id:
            self.block_id = build_block_id(self.agent_id, self.user_id, self.block_name)

    @property
    def pk(self) -> str:
        return f"Agent#{self.agent_id}#User#{self.user_id}"

    @property
    def sk(self) -> str:
        return f"CoreMemory#{self.block_id}"

    def compute_word_count(self) -> int:
        """Calculate total word count across all lines."""
        return sum(len(line.split()) for line in self.lines)

    def ensure_line_meta(self, now: Optional[datetime] = None) -> None:
        """Ensure line_meta exists and is aligned with lines."""
        if now is None:
            now = datetime.now(timezone.utc)

        if self.line_meta is None:
            self.line_meta = []

        # Extend meta for any missing entries
        while len(self.line_meta) < len(self.lines):
            self.line_meta.append(CoreMemoryLineMeta(created_at=now, last_accessed_at=None))

        # Trim meta if lines were trimmed elsewhere
        if len(self.line_meta) > len(self.lines):
            self.line_meta = self.line_meta[: len(self.lines)]

    def touch_all_lines(self, now: Optional[datetime] = None) -> None:
        """Mark all lines as accessed (used by LRU policy)."""
        if now is None:
            now = datetime.now(timezone.utc)
        self.ensure_line_meta(now=now)
        for meta in self.line_meta:
            meta.last_accessed_at = now

    def get_capacity_percent(self, word_limit: int) -> float:
        """Calculate capacity percentage based on word limit."""
        return (self.word_count / word_limit) * 100 if word_limit > 0 else 0

    def to_dynamo_item(self) -> dict:
        item = {
            "pk": self.pk,
            "sk": self.sk,
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "block_id": self.block_id,
            "block_name": self.block_name,
            "lines": self.lines,
            "line_meta": [m.model_dump() for m in self.line_meta] if self.line_meta else [],
            "word_count": self.word_count,
            "created_at": self.created_at.isoformat(),
        }
        if self.updated_at:
            item["updated_at"] = self.updated_at.isoformat()
        return item

    @classmethod
    def from_dynamo_item(cls, item: dict) -> "CoreMemory":
        return cls(
            agent_id=item["agent_id"],
            user_id=item["user_id"],
            block_id=item.get("block_id")
            or build_block_id(item["agent_id"], item["user_id"], item["block_name"]),
            block_name=item["block_name"],
            lines=item.get("lines", []),
            line_meta=[CoreMemoryLineMeta(**m) for m in (item.get("line_meta") or [])],
            word_count=item.get("word_count", 0),
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )


class ArchivalMemory(BaseModel):
    """
    Long-term memory that is searched on-demand via tool calls.

    Uses content hash for idempotent inserts.
    Supports paginated search results.
    """
    agent_id: str
    user_id: str
    memory_id: str = Field(default_factory=lambda: str(uuid4()))
    content: str
    content_hash: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def __init__(self, **data):
        super().__init__(**data)
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()

    @property
    def pk(self) -> str:
        return f"Agent#{self.agent_id}#User#{self.user_id}"

    @property
    def sk(self) -> str:
        return f"Archival#{self.created_at.isoformat()}#{self.memory_id}"

    @property
    def hash_pk(self) -> str:
        """PK for content hash lookup (idempotency)."""
        return f"Agent#{self.agent_id}#User#{self.user_id}#Hash#{self.content_hash}"

    @property
    def hash_sk(self) -> str:
        """SK for content hash lookup."""
        return f"Archival#{self.memory_id}"

    def to_dynamo_item(self) -> dict:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "memory_id": self.memory_id,
            "content": self.content,
            "content_hash": self.content_hash,
            "created_at": self.created_at.isoformat(),
        }

    def to_hash_index_item(self) -> dict:
        """Item for the content hash index (for idempotency lookups)."""
        return {
            "pk": self.hash_pk,
            "sk": self.hash_sk,
            "memory_id": self.memory_id,
            "agent_id": self.agent_id,
            "user_id": self.user_id,
        }

    @classmethod
    def from_dynamo_item(cls, item: dict) -> "ArchivalMemory":
        return cls(
            agent_id=item["agent_id"],
            user_id=item["user_id"],
            memory_id=item["memory_id"],
            content=item["content"],
            content_hash=item.get("content_hash", ""),
            created_at=datetime.fromisoformat(item["created_at"]),
        )


class CapacityWarningTracker(BaseModel):
    """
    Tracks how many turns a memory block has been at warning capacity.

    Used for auto-compaction: if warning_turns >= 3, trigger compaction.
    """
    agent_id: str
    user_id: str
    block_id: str = ""
    block_name: str
    warning_turns: int = 0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def __init__(self, **data):
        super().__init__(**data)
        if not self.block_id:
            self.block_id = build_block_id(self.agent_id, self.user_id, self.block_name)

    @property
    def pk(self) -> str:
        return f"Agent#{self.agent_id}#User#{self.user_id}"

    @property
    def sk(self) -> str:
        return f"CapacityWarning#{self.block_id}"

    def to_dynamo_item(self) -> dict:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "block_id": self.block_id,
            "block_name": self.block_name,
            "warning_turns": self.warning_turns,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dynamo_item(cls, item: dict) -> "CapacityWarningTracker":
        return cls(
            agent_id=item["agent_id"],
            user_id=item["user_id"],
            block_id=item.get("block_id")
            or build_block_id(item["agent_id"], item["user_id"], item["block_name"]),
            block_name=item["block_name"],
            warning_turns=item.get("warning_turns", 0),
            updated_at=datetime.fromisoformat(item["updated_at"]),
        )
