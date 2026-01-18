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

from pydantic import BaseModel, Field


class MemoryBlockDefinition(BaseModel):
    """
    Defines a memory block available to an agent.

    Default blocks are "human" and "persona".
    Users can create custom blocks with configurable word limits.
    """
    agent_id: str
    block_name: str
    description: str
    word_limit: int = 5000
    is_default: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def pk(self) -> str:
        return f"Agent#{self.agent_id}"

    @property
    def sk(self) -> str:
        return f"MemoryBlockDef#{self.block_name}"

    def to_dynamo_item(self) -> dict:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "agent_id": self.agent_id,
            "block_name": self.block_name,
            "description": self.description,
            "word_limit": self.word_limit,
            "is_default": self.is_default,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dynamo_item(cls, item: dict) -> "MemoryBlockDefinition":
        return cls(
            agent_id=item["agent_id"],
            block_name=item["block_name"],
            description=item["description"],
            word_limit=item.get("word_limit", 5000),
            is_default=item.get("is_default", False),
            created_at=datetime.fromisoformat(item["created_at"]),
        )


class CoreMemory(BaseModel):
    """
    In-context memory that is loaded into the system prompt every turn.

    Stores content as a list of lines for line-based editing.
    Tracks word count for capacity management.
    """
    agent_id: str
    block_name: str
    lines: list[str] = Field(default_factory=list)
    word_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"Agent#{self.agent_id}"

    @property
    def sk(self) -> str:
        return f"CoreMemory#{self.block_name}"

    def compute_word_count(self) -> int:
        """Calculate total word count across all lines."""
        return sum(len(line.split()) for line in self.lines)

    def get_capacity_percent(self, word_limit: int) -> float:
        """Calculate capacity percentage based on word limit."""
        return (self.word_count / word_limit) * 100 if word_limit > 0 else 0

    def to_dynamo_item(self) -> dict:
        item = {
            "pk": self.pk,
            "sk": self.sk,
            "agent_id": self.agent_id,
            "block_name": self.block_name,
            "lines": self.lines,
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
            block_name=item["block_name"],
            lines=item.get("lines", []),
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
        return f"Agent#{self.agent_id}"

    @property
    def sk(self) -> str:
        return f"Archival#{self.created_at.isoformat()}#{self.memory_id}"

    @property
    def hash_pk(self) -> str:
        """PK for content hash lookup (idempotency)."""
        return f"Agent#{self.agent_id}#Hash#{self.content_hash}"

    @property
    def hash_sk(self) -> str:
        """SK for content hash lookup."""
        return f"Archival#{self.memory_id}"

    def to_dynamo_item(self) -> dict:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "agent_id": self.agent_id,
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
        }

    @classmethod
    def from_dynamo_item(cls, item: dict) -> "ArchivalMemory":
        return cls(
            agent_id=item["agent_id"],
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
    block_name: str
    warning_turns: int = 0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def pk(self) -> str:
        return f"Agent#{self.agent_id}"

    @property
    def sk(self) -> str:
        return f"CapacityWarning#{self.block_name}"

    def to_dynamo_item(self) -> dict:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "agent_id": self.agent_id,
            "block_name": self.block_name,
            "warning_turns": self.warning_turns,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dynamo_item(cls, item: dict) -> "CapacityWarningTracker":
        return cls(
            agent_id=item["agent_id"],
            block_name=item["block_name"],
            warning_turns=item.get("warning_turns", 0),
            updated_at=datetime.fromisoformat(item["updated_at"]),
        )
