"""Request and response schemas of the public /v1 API.

These are a public contract: add fields freely, but never rename or remove one
without a new API version.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from src.agents.models import Agent
from src.conversations.models import ApiConversation
from src.messages.models import ImageAttachmentResponse, Message
from src.vision.policy import ImageInputAvailability, image_input_availability
from src.config import settings


def v1_image_url(agent_id: str, conversation_id: str, image_id: str) -> str:
    return f"{settings.api_base_url.rstrip('/')}/v1/agents/{agent_id}/conversations/{conversation_id}/images/{image_id}"


class V1AgentResponse(BaseModel):
    agent_id: str
    name: str
    description: Optional[str] = None
    #: Whether messages to this agent may carry images, and the limits an image must meet.
    image_input: ImageInputAvailability

    @classmethod
    def of(cls, agent: Agent) -> "V1AgentResponse":
        return cls(
            agent_id=agent.agent_id,
            name=agent.agent_name,
            description=agent.agent_description,
            image_input=image_input_availability(agent),
        )


class V1CreateConversationRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    end_user_id: Optional[str] = Field(
        None,
        min_length=1,
        max_length=200,
        description="Your identifier for the person chatting. Each end user gets their own agent memory.",
    )
    context: Optional[str] = Field(
        None, description="Sent to the agent on every turn of this conversation, so your messages need not repeat it."
    )


class V1UpdateConversationRequest(BaseModel):
    """Only the fields sent are changed; an empty body changes nothing."""

    context: Optional[str] = Field(None, description="Replaces the conversation's context.")


class V1ConversationResponse(BaseModel):
    conversation_id: str
    agent_id: str
    title: str
    end_user_id: Optional[str] = None
    context: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    @classmethod
    def of(cls, conversation: ApiConversation) -> "V1ConversationResponse":
        return cls(
            conversation_id=conversation.conversation_id,
            agent_id=conversation.agent_id,
            title=conversation.title,
            end_user_id=conversation.end_user_id,
            context=conversation.context,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


class V1MessageResponse(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    image_attachments: list[ImageAttachmentResponse] = Field(default_factory=list)

    @classmethod
    def of(cls, message: Message, agent_id: str) -> "V1MessageResponse":
        return cls(
            message_id=message.message_id,
            role=message.role,  # type: ignore[arg-type]  # system rows are filtered out before this
            content=message.content,
            created_at=message.created_at,
            image_attachments=[
                ImageAttachmentResponse(
                    **image.model_dump(include=set(ImageAttachmentResponse.model_fields) - {"url"}),
                    url=v1_image_url(agent_id, message.conversation_id, image.image_id),
                )
                for image in message.image_attachments
            ],
        )


class V1SendMessageRequest(BaseModel):
    content: str = ""
    image_ids: list[str] = Field(
        default_factory=list,
        description="Images uploaded to this conversation with `POST .../images`, sent with the message.",
    )
    stream: bool = Field(True, description="Stream the reply as Server-Sent Events, or wait and return it whole.")

    @model_validator(mode="after")
    def require_text_or_image(self) -> "V1SendMessageRequest":
        if not self.content.strip() and not self.image_ids:
            raise ValueError("A message needs content or image_ids")
        return self


class V1SendMessageResponse(BaseModel):
    conversation_id: str
    turn_id: str
    user_message_id: Optional[str] = None
    assistant_message_id: Optional[str] = None
    text: str
