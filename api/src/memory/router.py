"""
Memory block management API.

Provides endpoints for users to manage custom memory blocks per agent.
"""

import logging
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

from src.agents.repository import AgentRepository
from .models import MemoryBlockDefinition
from .repository import MemoryRepository

log = logging.getLogger(__name__)

security = HTTPBearer()

router = APIRouter(
    prefix="/agents/{agent_id}/memory-blocks",
    tags=["memory"],
    dependencies=[Depends(security)],
)


# Request/Response models
class CreateMemoryBlockRequest(BaseModel):
    """Request body for creating a custom memory block."""
    name: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(..., min_length=1, max_length=200)
    word_limit: int = Field(default=5000, ge=100, le=50000)


class MemoryBlockResponse(BaseModel):
    """Response model for memory block information."""
    block_name: str
    description: str
    word_limit: int
    is_default: bool
    word_count: int
    capacity_percent: float
    created_at: datetime


class MemoryBlockContentResponse(BaseModel):
    """Response model for memory block content."""
    block_name: str
    lines: list[str]
    word_count: int
    word_limit: int
    capacity_percent: float
    is_default: bool


class UpdateMemoryBlockContentRequest(BaseModel):
    """Request body for updating memory block content."""
    lines: list[str] = Field(..., description="Lines of content for the memory block")


def get_memory_repository() -> MemoryRepository:
    return MemoryRepository()


def get_agent_repository() -> AgentRepository:
    return AgentRepository()


@router.get("", response_model=list[MemoryBlockResponse])
async def list_memory_blocks(
    request: Request,
    agent_id: str,
    memory_repo: Annotated[MemoryRepository, Depends(get_memory_repository)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> list[MemoryBlockResponse]:
    """
    List all memory blocks for an agent.

    Returns both default blocks (human, persona) and any custom blocks.
    """
    user_id: str = request.state.user_email

    # Verify agent ownership
    agent = agent_repo.find_agent_by_id(agent_id, user_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Get block definitions
    block_defs = memory_repo.get_block_definitions(agent_id, user_id)
    if not block_defs:
        # Initialize default blocks if none exist
        memory_repo.initialize_default_blocks(agent_id, user_id)
        block_defs = memory_repo.get_block_definitions(agent_id, user_id)

    # Get memory content for capacity info
    memories = {
        m.block_name: m for m in memory_repo.get_all_core_memories(agent_id, user_id)
    }

    result = []
    for block_def in block_defs:
        memory = memories.get(block_def.block_name)
        word_count = memory.word_count if memory else 0
        capacity_percent = (
            (word_count / block_def.word_limit) * 100
            if block_def.word_limit > 0
            else 0
        )

        result.append(
            MemoryBlockResponse(
                block_name=block_def.block_name,
                description=block_def.description,
                word_limit=block_def.word_limit,
                is_default=block_def.is_default,
                word_count=word_count,
                capacity_percent=capacity_percent,
                created_at=block_def.created_at,
            )
        )

    return result


@router.post(
    "",
    response_model=MemoryBlockResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_memory_block(
    request: Request,
    agent_id: str,
    body: CreateMemoryBlockRequest,
    memory_repo: Annotated[MemoryRepository, Depends(get_memory_repository)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> MemoryBlockResponse:
    """
    Create a custom memory block for an agent.

    Block names must be lowercase with underscores, e.g., "projects", "goals".
    Default word limit is 5000.
    """
    user_id: str = request.state.user_email

    # Verify agent ownership
    agent = agent_repo.find_agent_by_id(agent_id, user_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Check if block already exists
    existing = memory_repo.get_block_definition(agent_id, user_id, body.name)
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Memory block '{body.name}' already exists",
        )

    # Reserved names
    if body.name in ("human", "persona"):
        raise HTTPException(
            status_code=400,
            detail=f"'{body.name}' is a reserved block name",
        )

    # Create block definition
    block_def = MemoryBlockDefinition(
        agent_id=agent_id,
        user_id=user_id,
        block_name=body.name,
        description=body.description,
        word_limit=body.word_limit,
        is_default=False,
    )
    memory_repo.save_block_definition(block_def)

    log.info(f"Created custom memory block '{body.name}' for agent {agent_id}")

    return MemoryBlockResponse(
        block_name=block_def.block_name,
        description=block_def.description,
        word_limit=block_def.word_limit,
        is_default=block_def.is_default,
        word_count=0,
        capacity_percent=0,
        created_at=block_def.created_at,
    )


@router.delete("/{block_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory_block(
    request: Request,
    agent_id: str,
    block_name: str,
    memory_repo: Annotated[MemoryRepository, Depends(get_memory_repository)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> None:
    """
    Delete a custom memory block.

    Cannot delete default blocks (human, persona).
    This is idempotent - returns success even if block doesn't exist.
    """
    user_id: str = request.state.user_email

    # Verify agent ownership
    agent = agent_repo.find_agent_by_id(agent_id, user_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Check if it's a default block
    block_def = memory_repo.get_block_definition(agent_id, user_id, block_name)
    if block_def and block_def.is_default:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete default memory block '{block_name}'",
        )

    # Delete (idempotent)
    memory_repo.delete_block_definition(agent_id, user_id, block_name)
    log.info(f"Deleted memory block '{block_name}' for agent {agent_id}")


@router.get("/{block_name}/content", response_model=MemoryBlockContentResponse)
async def get_memory_block_content(
    request: Request,
    agent_id: str,
    block_name: str,
    memory_repo: Annotated[MemoryRepository, Depends(get_memory_repository)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> MemoryBlockContentResponse:
    """
    Get the content (lines) of a memory block.

    Returns the actual memory content stored in the block.
    """
    user_id: str = request.state.user_email

    # Verify agent ownership
    agent = agent_repo.find_agent_by_id(agent_id, user_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Get block definition
    block_def = memory_repo.get_block_definition(agent_id, user_id, block_name)
    if not block_def:
        raise HTTPException(status_code=404, detail=f"Memory block '{block_name}' not found")

    # Get memory content
    memory = memory_repo.get_core_memory(agent_id, user_id, block_name)
    lines = memory.lines if memory else []
    word_count = memory.word_count if memory else 0
    capacity_percent = (
        (word_count / block_def.word_limit) * 100
        if block_def.word_limit > 0
        else 0
    )

    return MemoryBlockContentResponse(
        block_name=block_name,
        lines=lines,
        word_count=word_count,
        word_limit=block_def.word_limit,
        capacity_percent=capacity_percent,
        is_default=block_def.is_default,
    )


@router.put("/{block_name}/content", response_model=MemoryBlockContentResponse)
async def update_memory_block_content(
    request: Request,
    agent_id: str,
    block_name: str,
    body: UpdateMemoryBlockContentRequest,
    memory_repo: Annotated[MemoryRepository, Depends(get_memory_repository)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> MemoryBlockContentResponse:
    """
    Update the content (lines) of a custom memory block.

    Users can only edit custom blocks they created, not default blocks (human, persona).
    """
    user_id: str = request.state.user_email

    # Verify agent ownership
    agent = agent_repo.find_agent_by_id(agent_id, user_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Get block definition
    block_def = memory_repo.get_block_definition(agent_id, user_id, block_name)
    if not block_def:
        raise HTTPException(status_code=404, detail=f"Memory block '{block_name}' not found")

    # Cannot edit default blocks
    if block_def.is_default:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit default memory block '{block_name}'. Only custom blocks can be edited.",
        )

    # Get or create memory content
    from .models import CoreMemory
    memory = memory_repo.get_core_memory(agent_id, user_id, block_name)
    if not memory:
        memory = CoreMemory(agent_id=agent_id, user_id=user_id, block_name=block_name)

    # Update content
    memory.lines = body.lines
    memory.word_count = memory.compute_word_count()
    memory_repo.save_core_memory(memory)

    capacity_percent = (
        (memory.word_count / block_def.word_limit) * 100
        if block_def.word_limit > 0
        else 0
    )

    log.info(f"Updated content for memory block '{block_name}' in agent {agent_id}")

    return MemoryBlockContentResponse(
        block_name=block_name,
        lines=memory.lines,
        word_count=memory.word_count,
        word_limit=block_def.word_limit,
        capacity_percent=capacity_percent,
        is_default=block_def.is_default,
    )
