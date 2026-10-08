"""A building conversation with Ada, and the blueprint she is working on in it."""

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class BuilderSession(BaseModel):
    """
    One conversation with Ada. Holds the draft between turns: chat history keeps only the messages,
    not Ada's tool calls, so the blueprint she planned would otherwise be lost to her next turn.

    DynamoDB: pk=User#{user_email}, sk=BuilderSession#{conversation_id}
    """

    conversation_id: str
    user_email: str
    #: The owner's own provider and model; Ada runs on them like any of their agents.
    provider: str
    model: Optional[str] = None
    draft_yaml: Optional[str] = None
    draft_params: dict[str, Any] = Field(default_factory=dict)
    #: Set when the draft last planned without blockers; apply needs the person to approve this id.
    plan_id: Optional[str] = None
    deployment_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"User#{self.user_email}"

    @property
    def sk(self) -> str:
        return f"BuilderSession#{self.conversation_id}"


class CreateBuilderSessionRequest(BaseModel):
    agent_provider: str
    agent_model: Optional[str] = None


class BuilderSessionResponse(BaseModel):
    conversation_id: str
    provider: str
    model: Optional[str] = None
    deployment_id: Optional[str] = None
    created_at: datetime
