"""Request and response schemas of the public /v1 API.

These are a public contract: add fields freely, but never rename or remove one
without a new API version.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.agents.models import Agent
from src.conversations.models import ApiConversation
from src.messages.models import Message


class V1AgentResponse(BaseModel):
    agent_id: str
    name: str
    description: Optional[str] = None

    @classmethod
    def of(cls, agent: Agent) -> "V1AgentResponse":
        return cls(agent_id=agent.agent_id, name=agent.agent_name, description=agent.agent_description)


class V1CreateConversationRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    end_user_id: Optional[str] = Field(
        None,
        min_length=1,
        max_length=200,
        description="Your identifier for the person chatting. Each end user gets their own agent memory.",
    )


class V1ConversationResponse(BaseModel):
    conversation_id: str
    agent_id: str
    title: str
    end_user_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    @classmethod
    def of(cls, conversation: ApiConversation) -> "V1ConversationResponse":
        return cls(
            conversation_id=conversation.conversation_id,
            agent_id=conversation.agent_id,
            title=conversation.title,
            end_user_id=conversation.end_user_id,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


class V1MessageResponse(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime

    @classmethod
    def of(cls, message: Message) -> "V1MessageResponse":
        return cls(
            message_id=message.message_id,
            role=message.role,  # type: ignore[arg-type]  # system rows are filtered out before this
            content=message.content,
            created_at=message.created_at,
        )


class V1SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1)
    stream: bool = Field(True, description="Stream the reply as Server-Sent Events, or wait and return it whole.")


class V1SendMessageResponse(BaseModel):
    conversation_id: str
    turn_id: str
    user_message_id: Optional[str] = None
    assistant_message_id: Optional[str] = None
    text: str
