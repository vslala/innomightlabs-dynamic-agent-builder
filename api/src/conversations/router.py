"""
Conversations API router.
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from src.agents.image_generation.storage import ConversationMediaStorage
from src.agents.access import require_agent
from src.agents.repository import AgentRepository
from src.common.pagination import Paginated
from src.conversations.models import (
    Conversation,
    ConversationResponse,
    CreateConversationRequest,
    UpdateConversationRequest,
)
from src.builder.models import ILA_AGENT_ID
from src.conversations.repository import ConversationRepository
from src.accounts.owner import member_partition
from src.iam.dependencies import get_principal
from src.iam.principal import Principal
from src.messages.models import Message, MessageResponse
from src.messages.repositories import get_message_repository
from src.messages.responses import MessageResponseFactory

router = APIRouter(prefix="/conversations", tags=["conversations"])

# Initialize repositories
conversation_repository = ConversationRepository()
agent_repository = AgentRepository()
message_repository = get_message_repository("dynamodb")
message_response_factory = MessageResponseFactory()


def own_partition(principal: Annotated[Principal, Depends(get_principal)]) -> str:
    """The caller's own conversations in the account they act in: nobody else's, even an admin's."""
    return member_partition(principal.account_id, principal.user_id)


Partition = Annotated[str, Depends(own_partition)]


def validate_agent(agent_id: str, principal: Principal) -> None:
    """The caller may chat with the agent: their own, or one shared with them."""
    require_agent(principal, agent_id, "agents:Chat", agent_repository)


def find_visible_messages_newest_first(
    conversation_id: str,
    *,
    limit: int,
    cursor: Optional[str],
) -> tuple[list[Message], Optional[str], bool]:
    """A full page of chat messages, newest first.

    Tool-call audit rows are written on the AUDIT# prefix and so never appear
    in this query. The paging loop below exists only for rows written before
    that split, which are still `role="system"` under MESSAGE#; without it a
    tool-heavy stretch of an old conversation could return an empty page while
    reporting has_more. It collapses to one iteration for everything newer.
    """
    visible_messages: list[Message] = []
    next_cursor = cursor
    has_more = True

    while len(visible_messages) < limit and has_more:
        page_limit = max(1, limit - len(visible_messages))
        page_messages, next_cursor, has_more = (
            message_repository.find_by_conversation_newest_first(
                conversation_id=conversation_id,
                limit=page_limit,
                cursor=next_cursor,
            )
        )
        visible_messages.extend(
            message for message in page_messages if message.role != "system"
        )

    return visible_messages[:limit], next_cursor, has_more


@router.post("/", response_model=ConversationResponse, status_code=201)
async def create_conversation(body: CreateConversationRequest, principal: Annotated[Principal, Depends(get_principal)]):
    """
    Create a new conversation.

    - **title**: Title of the conversation (required)
    - **description**: Optional description
    - **agent_id**: ID of the agent to manage this conversation (must exist and belong to user)
    - **context**: Optional context sent to the agent on every turn
    """
    validate_agent(body.agent_id, principal)

    # Create conversation
    conversation = Conversation(
        title=body.title,
        description=body.description,
        agent_id=body.agent_id,
        account_id=principal.account_id,
        created_by=principal.user_id,
        context=body.context,
    )

    saved = conversation_repository.save(conversation)
    return saved.to_response()


@router.get("/", response_model=Paginated[ConversationResponse])
async def list_conversations(
    partition: Partition,
    limit: int = Query(default=10, ge=1, le=100, description="Number of items per page"),
    cursor: Optional[str] = Query(default=None, description="Pagination cursor"),
    include_automation: bool = Query(
        default=False,
        description="Include automation-run conversations in the response",
    ),
):
    """
    List all conversations for the current user.

    Returns conversations ordered by last activity (most recently updated or
    created first). Supports cursor-based pagination.
    """

    def keep(conversation: Conversation) -> bool:
        # Building with Ila has its own page; her conversations aren't chats with the person's agents.
        if conversation.agent_id == ILA_AGENT_ID:
            return False
        return include_automation or getattr(conversation, "conversation_type", "chat") != "automation"

    conversations, next_cursor, has_more = conversation_repository.find_all_by_user_paginated(
        partition, limit=limit, cursor=cursor, keep=keep
    )

    return Paginated[ConversationResponse](
        items=[c.to_response() for c in conversations],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str, partition: Partition):
    """
    Get a specific conversation by ID.
    """

    conversation = conversation_repository.find_by_id(conversation_id, partition)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation.to_response()


@router.get("/{conversation_id}/messages", response_model=Paginated[MessageResponse])
async def get_messages(
    partition: Partition,
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

    # Verify conversation exists and belongs to user
    conversation = conversation_repository.find_by_id(conversation_id, partition)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    visible_messages, next_cursor, has_more = find_visible_messages_newest_first(
        conversation_id=conversation_id,
        limit=limit,
        cursor=cursor,
    )

    return Paginated[MessageResponse](
        items=[message_response_factory.to_response(m) for m in visible_messages],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/{conversation_id}/tool-audit", response_model=Paginated[MessageResponse])
async def get_tool_audit(
    partition: Partition,
    conversation_id: str,
    limit: int = Query(default=20, ge=1, le=100, description="Audit rows per page"),
    cursor: Optional[str] = Query(default=None, description="Pagination cursor for older rows"),
):
    """The conversation's tool-call audit trail, newest first.

    Each row's `content` is a serialized ToolCallAuditMessage. Kept out of
    `/messages` because nothing renders it -- this is for inspecting what an
    agent actually called and what came back.
    """

    conversation = conversation_repository.find_by_id(conversation_id, partition)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    audit_rows, next_cursor, has_more = message_repository.find_audit_by_conversation(
        conversation_id=conversation_id,
        limit=limit,
        cursor=cursor,
    )

    return Paginated[MessageResponse](
        items=[message_response_factory.to_response(row) for row in audit_rows],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/{conversation_id}/messages/{message_id}/images/{image_id}")
async def get_message_image(
    partition: Partition,
    conversation_id: str,
    message_id: str,
    image_id: str,
):
    """Return generated image bytes for an authenticated conversation owner."""

    conversation = conversation_repository.find_by_id(conversation_id, partition)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = message_repository.find_by_conversation(conversation_id)
    message = next((m for m in messages if m.message_id == message_id), None)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    image = next((img for img in message.images if img.image_id == image_id), None)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    try:
        stored_image = ConversationMediaStorage().get_image(image.s3_key)
    except Exception as e:
        raise HTTPException(status_code=404, detail="Image object not found") from e

    return Response(
        content=stored_image.body,
        media_type=stored_image.content_type,
        headers={
            "Cache-Control": "private, max-age=300",
            "Content-Disposition": f'inline; filename="{image.filename}"',
        },
    )


@router.put("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: str, body: UpdateConversationRequest, partition: Partition,
    principal: Annotated[Principal, Depends(get_principal)],
):
    """
    Update a conversation.

    - **title**: New title (optional)
    - **description**: New description (optional)
    - **agent_id**: New agent ID (optional, must exist and belong to user)
    - **context**: New conversation context (optional)
    """

    # Find existing conversation
    conversation = conversation_repository.find_by_id(conversation_id, partition)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Validate new agent if provided
    if body.agent_id is not None:
        validate_agent(body.agent_id, principal)
        conversation.agent_id = body.agent_id

    # Update fields if provided
    if body.title is not None:
        conversation.title = body.title

    if body.description is not None:
        conversation.description = body.description

    if body.context is not None:
        conversation.context = body.context

    saved = conversation_repository.save(conversation)
    return saved.to_response()


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, partition: Partition):
    """
    Delete a conversation.

    This will permanently delete the conversation and all its messages.
    """

    # Check if conversation exists
    conversation = conversation_repository.find_by_id(conversation_id, partition)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Delete all messages in this conversation first
    deleted_messages = message_repository.delete_by_conversation(conversation_id)

    try:
        ConversationMediaStorage().delete_conversation_prefix(
            conversation.agent_id,
            conversation_id,
        )
    except Exception:
        # Do not leave a user-visible deletion failure after DynamoDB cleanup
        # succeeded. S3 cleanup can be retried operationally by prefix.
        import logging

        logging.getLogger(__name__).warning(
            "Failed to delete media for conversation %s", conversation_id, exc_info=True
        )

    # Delete conversation
    deleted = conversation_repository.delete_by_id(conversation_id, partition)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete conversation")

    return None
