"""
Memory repository for DynamoDB operations.

Handles CRUD operations for:
- MemoryBlockDefinition
- CoreMemory
- ArchivalMemory
- CapacityWarningTracker
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key, Attr

from src.config import settings
from .models import (
    MemoryBlockDefinition,
    CoreMemory,
    ArchivalMemory,
    CapacityWarningTracker,
)

log = logging.getLogger(__name__)


class MemoryRepository:
    """Repository for memory operations in DynamoDB."""

    def __init__(self):
        self.dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    # =========================================================================
    # Memory Block Definitions
    # =========================================================================

    def get_block_definitions(self, agent_id: str) -> list[MemoryBlockDefinition]:
        """Get all memory block definitions for an agent."""
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"Agent#{agent_id}")
            & Key("sk").begins_with("MemoryBlockDef#")
        )
        return [
            MemoryBlockDefinition.from_dynamo_item(item)
            for item in response.get("Items", [])
        ]

    def get_block_definition(
        self, agent_id: str, block_name: str
    ) -> Optional[MemoryBlockDefinition]:
        """Get a specific memory block definition."""
        response = self.table.get_item(
            Key={
                "pk": f"Agent#{agent_id}",
                "sk": f"MemoryBlockDef#{block_name}",
            }
        )
        item = response.get("Item")
        return MemoryBlockDefinition.from_dynamo_item(item) if item else None

    def save_block_definition(
        self, block_def: MemoryBlockDefinition
    ) -> MemoryBlockDefinition:
        """Save a memory block definition."""
        self.table.put_item(Item=block_def.to_dynamo_item())
        log.info(f"Saved block definition: {block_def.block_name} for agent {block_def.agent_id}")
        return block_def

    def delete_block_definition(self, agent_id: str, block_name: str) -> bool:
        """Delete a memory block definition (only custom blocks)."""
        block_def = self.get_block_definition(agent_id, block_name)
        if not block_def:
            return True  # Idempotent
        if block_def.is_default:
            raise ValueError(f"Cannot delete default block: {block_name}")

        self.table.delete_item(
            Key={
                "pk": f"Agent#{agent_id}",
                "sk": f"MemoryBlockDef#{block_name}",
            }
        )
        # Also delete the core memory content
        self.table.delete_item(
            Key={
                "pk": f"Agent#{agent_id}",
                "sk": f"CoreMemory#{block_name}",
            }
        )
        log.info(f"Deleted block definition: {block_name} for agent {agent_id}")
        return True

    def initialize_default_blocks(self, agent_id: str) -> None:
        """Create default 'human' and 'persona' blocks for an agent."""
        defaults = [
            MemoryBlockDefinition(
                agent_id=agent_id,
                block_name="human",
                description="Facts about the user",
                word_limit=5000,
                is_default=True,
            ),
            MemoryBlockDefinition(
                agent_id=agent_id,
                block_name="persona",
                description="Your traits and characteristics",
                word_limit=5000,
                is_default=True,
            ),
        ]
        for block_def in defaults:
            # Only create if doesn't exist (idempotent)
            if not self.get_block_definition(agent_id, block_def.block_name):
                self.save_block_definition(block_def)
        log.info(f"Initialized default memory blocks for agent {agent_id}")

    # =========================================================================
    # Core Memory
    # =========================================================================

    def get_core_memory(self, agent_id: str, block_name: str) -> Optional[CoreMemory]:
        """Get core memory for a specific block."""
        response = self.table.get_item(
            Key={
                "pk": f"Agent#{agent_id}",
                "sk": f"CoreMemory#{block_name}",
            }
        )
        item = response.get("Item")
        return CoreMemory.from_dynamo_item(item) if item else None

    def get_all_core_memories(self, agent_id: str) -> list[CoreMemory]:
        """Get all core memories for an agent."""
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"Agent#{agent_id}")
            & Key("sk").begins_with("CoreMemory#")
        )
        return [CoreMemory.from_dynamo_item(item) for item in response.get("Items", [])]

    def save_core_memory(self, memory: CoreMemory) -> CoreMemory:
        """Save core memory content."""
        # Ensure word count is current
        memory.word_count = memory.compute_word_count()
        memory.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=memory.to_dynamo_item())
        log.info(
            f"Saved core memory [{memory.block_name}] for agent {memory.agent_id}: "
            f"{len(memory.lines)} lines, {memory.word_count} words"
        )
        return memory

    def line_exists(
        self, agent_id: str, block_name: str, content: str
    ) -> Optional[int]:
        """
        Check if a line with this content already exists.

        Returns:
            Line number (1-indexed) if exists, None otherwise.
        """
        memory = self.get_core_memory(agent_id, block_name)
        if not memory:
            return None

        # Normalize content for comparison
        normalized_content = content.strip()
        for i, line in enumerate(memory.lines):
            if line.strip() == normalized_content:
                return i + 1  # 1-indexed

        return None

    # =========================================================================
    # Archival Memory
    # =========================================================================

    def find_archival_by_hash(
        self, agent_id: str, content_hash: str
    ) -> Optional[ArchivalMemory]:
        """Find archival memory by content hash (for idempotency)."""
        # Query using the hash PK pattern
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"Agent#{agent_id}#Hash#{content_hash}")
        )
        items = response.get("Items", [])
        if not items:
            return None

        # Get the actual archival memory using the memory_id
        memory_id = items[0].get("memory_id")
        if not memory_id:
            return None

        # Query for the actual archival item
        archival_response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"Agent#{agent_id}")
            & Key("sk").begins_with(f"Archival#"),
            FilterExpression=Attr("memory_id").eq(memory_id),
        )
        archival_items = archival_response.get("Items", [])
        if archival_items:
            return ArchivalMemory.from_dynamo_item(archival_items[0])
        return None

    def insert_archival(
        self, agent_id: str, content: str
    ) -> tuple[ArchivalMemory, bool]:
        """
        Insert archival memory with idempotency.

        Returns:
            Tuple of (ArchivalMemory, is_new) where is_new=False if duplicate.
        """
        # Calculate hash for idempotency check
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Check if already exists
        existing = self.find_archival_by_hash(agent_id, content_hash)
        if existing:
            log.info(f"Archival memory already exists: {existing.memory_id}")
            return existing, False

        # Create new archival memory
        memory = ArchivalMemory(
            agent_id=agent_id,
            content=content,
            content_hash=content_hash,
        )

        # Save the archival memory
        self.table.put_item(Item=memory.to_dynamo_item())

        # Save the hash index for idempotency lookups
        self.table.put_item(Item=memory.to_hash_index_item())

        log.info(f"Created archival memory: {memory.memory_id} for agent {agent_id}")
        return memory, True

    def search_archival(
        self, agent_id: str, query: str, page: int = 1, page_size: int = 5
    ) -> tuple[list[ArchivalMemory], int]:
        """
        Search archival memory by query string.

        Returns:
            Tuple of (results, total_count).

        Note: This is a simple contains search. For production, consider
        using OpenSearch or similar for better search capabilities.
        """
        # Query all archival memories for this agent
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"Agent#{agent_id}")
            & Key("sk").begins_with("Archival#"),
            ScanIndexForward=False,  # Most recent first
        )

        all_items = response.get("Items", [])

        # Filter by query (case-insensitive contains)
        query_lower = query.lower()
        matching_items = [
            item for item in all_items
            if query_lower in item.get("content", "").lower()
        ]

        total = len(matching_items)

        # Paginate
        start = (page - 1) * page_size
        end = start + page_size
        page_items = matching_items[start:end]

        return [ArchivalMemory.from_dynamo_item(item) for item in page_items], total

    def delete_archival(self, agent_id: str, memory_id: str) -> bool:
        """Delete an archival memory by ID."""
        # First find the memory to get its sort key
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"Agent#{agent_id}")
            & Key("sk").begins_with("Archival#"),
            FilterExpression=Attr("memory_id").eq(memory_id),
        )
        items = response.get("Items", [])
        if not items:
            return True  # Idempotent

        item = items[0]
        content_hash = item.get("content_hash", "")

        # Delete the archival memory
        self.table.delete_item(
            Key={
                "pk": item["pk"],
                "sk": item["sk"],
            }
        )

        # Delete the hash index entry
        if content_hash:
            self.table.delete_item(
                Key={
                    "pk": f"Agent#{agent_id}#Hash#{content_hash}",
                    "sk": f"Archival#{memory_id}",
                }
            )

        log.info(f"Deleted archival memory: {memory_id}")
        return True

    # =========================================================================
    # Capacity Warning Tracker
    # =========================================================================

    def get_warning_tracker(
        self, agent_id: str, block_name: str
    ) -> Optional[CapacityWarningTracker]:
        """Get capacity warning tracker for a block."""
        response = self.table.get_item(
            Key={
                "pk": f"Agent#{agent_id}",
                "sk": f"CapacityWarning#{block_name}",
            }
        )
        item = response.get("Item")
        return CapacityWarningTracker.from_dynamo_item(item) if item else None

    def increment_warning_turns(self, agent_id: str, block_name: str) -> int:
        """Increment warning turns and return new count."""
        tracker = self.get_warning_tracker(agent_id, block_name)
        if tracker:
            tracker.warning_turns += 1
            tracker.updated_at = datetime.now(timezone.utc)
        else:
            tracker = CapacityWarningTracker(
                agent_id=agent_id,
                block_name=block_name,
                warning_turns=1,
            )

        self.table.put_item(Item=tracker.to_dynamo_item())
        log.info(f"Warning turns for [{block_name}]: {tracker.warning_turns}")
        return tracker.warning_turns

    def reset_warning_turns(self, agent_id: str, block_name: str) -> None:
        """Reset warning turns when capacity drops below threshold."""
        self.table.delete_item(
            Key={
                "pk": f"Agent#{agent_id}",
                "sk": f"CapacityWarning#{block_name}",
            }
        )
        log.info(f"Reset warning turns for [{block_name}]")

    def get_warning_turns(self, agent_id: str, block_name: str) -> int:
        """Get current warning turns count."""
        tracker = self.get_warning_tracker(agent_id, block_name)
        return tracker.warning_turns if tracker else 0
