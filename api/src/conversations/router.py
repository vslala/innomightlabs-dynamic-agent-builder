"""
Conversations API router.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from src.agents.repository import AgentRepository
from src.common.pagination import Paginated
from src.conversations.models import (
    Conversation,
    ConversationResponse,
    CreateConversationRequest,
    UpdateConversationRequest,
)
from src.conversations.repository import ConversationRepository
from src.messages.models import MessageResponse
from src.messages.repository import MessageRepository

router = APIRouter(prefix="/conversations", tags=["conversations"])

# Initialize repositories
conversation_repository = ConversationRepository()
agent_repository = AgentRepository()
message_repository = MessageRepository()


def get_user_email(request: Request) -> str:
    """Extract user email from request state (set by auth middleware)."""
    user_email = getattr(request.state, "user_email", None)
    if not user_email:
        raise HTTPException(status_code=401, detail="User not authenticated")
    return str(user_email)


def validate_agent(agent_id: str, user_email: str) -> None:
    """Validate that agent exists and belongs to the user."""
    agent = agent_repository.find_agent_by_id(agent_id, user_email)
    if not agent:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' not found or does not belong to you",
        )


@router.post("/", response_model=ConversationResponse, status_code=201)
async def create_conversation(request: Request, body: CreateConversationRequest):
    """
    Create a new conversation.

    - **title**: Title of the conversation (required)
    - **description**: Optional description
    - **agent_id**: ID of the agent to manage this conversation (must exist and belong to user)
    """
    user_email = get_user_email(request)

    # Validate agent exists and belongs to user
    validate_agent(body.agent_id, user_email)

    # Create conversation
    conversation = Conversation(
        title=body.title,
        description=body.description,
        agent_id=body.agent_id,
        created_by=user_email,
    )

    saved = conversation_repository.save(conversation)
    return saved.to_response()


@router.get("/", response_model=Paginated[ConversationResponse])
async def list_conversations(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100, description="Number of items per page"),
    cursor: Optional[str] = Query(default=None, description="Pagination cursor"),
):
    """
    List all conversations for the current user.

    Returns conversations in reverse chronological order (most recent first).
    Supports cursor-based pagination.
    """
    user_email = get_user_email(request)

    conversations, next_cursor, has_more = conversation_repository.find_all_by_user_paginated(
        created_by=user_email, limit=limit, cursor=cursor
    )

    return Paginated[ConversationResponse](
        items=[c.to_response() for c in conversations],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(request: Request, conversation_id: str):
    """
    Get a specific conversation by ID.
    """
    user_email = get_user_email(request)

    conversation = conversation_repository.find_by_id(conversation_id, user_email)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation.to_response()


@router.get("/{conversation_id}/messages", response_model=Paginated[MessageResponse])
async def get_messages(
    request: Request,
    conversation_id: str,
    limit: int = Query(default=20, ge=1, le=100, description="Number of messages per page"),
    cursor: Optional[str] = Query(default=None, description="Pagination cursor for older messages"),
):
    """
    Get messages for a conversation.

    Returns messages in reverse chronological order (newest first).
    Use cursor to load older messages (for infinite scroll up).

    The frontend should reverse the returned messages for display
    (oldest at top, newest at bottom).
    """
    user_email = get_user_email(request)

    # Verify conversation exists and belongs to user
    conversation = conversation_repository.find_by_id(conversation_id, user_email)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Get messages (newest first)
    messages, next_cursor, has_more = message_repository.find_by_conversation_newest_first(
        conversation_id=conversation_id, limit=limit, cursor=cursor
    )

    return Paginated[MessageResponse](
        items=[m.to_response() for m in messages],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.put("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    request: Request, conversation_id: str, body: UpdateConversationRequest
):
    """
    Update a conversation.

    - **title**: New title (optional)
    - **description**: New description (optional)
    - **agent_id**: New agent ID (optional, must exist and belong to user)
    """
    user_email = get_user_email(request)

    # Find existing conversation
    conversation = conversation_repository.find_by_id(conversation_id, user_email)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Validate new agent if provided
    if body.agent_id is not None:
        validate_agent(body.agent_id, user_email)
        conversation.agent_id = body.agent_id

    # Update fields if provided
    if body.title is not None:
        conversation.title = body.title

    if body.description is not None:
        conversation.description = body.description

    saved = conversation_repository.save(conversation)
    return saved.to_response()


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(request: Request, conversation_id: str):
    """
    Delete a conversation.

    This will permanently delete the conversation and all its messages.
    """
    user_email = get_user_email(request)

    # Check if conversation exists
    conversation = conversation_repository.find_by_id(conversation_id, user_email)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Delete all messages in this conversation first
    deleted_messages = message_repository.delete_by_conversation(conversation_id)

    # Delete conversation
    deleted = conversation_repository.delete_by_id(conversation_id, user_email)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete conversation")

    return None
