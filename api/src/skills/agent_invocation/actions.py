from __future__ import annotations

from typing import Any

from src.agents.architectures import get_agent_architecture
from src.agents.repository import AgentRepository
from src.conversations.models import Conversation
from src.conversations.repository import ConversationRepository
from src.llm.events import recorded_events
from src.messages.repositories import get_message_repository
from src.skills.agent_invocation.models import InvokeAgentRequest
from src.skills.models import ActorKind


async def invoke(
    arguments: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    request = InvokeAgentRequest.model_validate(arguments)
    target_agent_id = _target_agent_id(request, config, context)
    if not target_agent_id:
        raise ValueError("Missing target agent configuration")
    owner_email = str(context.get("owner_email") or "").strip()
    actor_email = str(context.get("actor_email") or owner_email).strip()
    actor_id = str(context.get("actor_id") or actor_email).strip()
    conversation_id = str(context.get("conversation_id") or "").strip()
    if not owner_email:
        raise ValueError("Missing skill runtime owner context")
    if not conversation_id:
        raise ValueError("Missing automation conversation context")

    agent = AgentRepository().find_agent_by_id(target_agent_id, owner_email)
    if not agent:
        raise ValueError("Agent not found")

    conversation = ConversationRepository().find_by_id(conversation_id, owner_email)
    if not isinstance(conversation, Conversation):
        raise ValueError("Conversation not found")

    architecture = get_agent_architecture(
        agent.agent_architecture,
        message_repository=get_message_repository("in_memory"),
    )
    invocation = await architecture.handle_message_buffered(
        agent=agent,
        conversation=conversation,
        user_message=request.prompt_template,
        owner_email=owner_email,
        actor_email=actor_email,
        actor_id=actor_id,
        actor_kind=ActorKind(context.get("actor_kind") or ActorKind.OWNER),
    )

    if not invocation.success:
        raise ValueError(invocation.error or "Agent invocation failed")

    return {
        "response_text": invocation.response_text,
        "events": recorded_events(invocation.events),
        "message_ids": {
            key: value
            for key, value in {
                "user_message_id": invocation.user_message_id,
                "assistant_message_id": invocation.assistant_message_id,
            }.items()
            if value
        },
    }


def _target_agent_id(request: InvokeAgentRequest, config: dict[str, Any], context: dict[str, Any]) -> str:
    """An automation step names its agent in the owner's own workflow. In a chat the model writes
    the arguments, so the agent the skill was installed for is the only one it can reach."""
    if context.get("orchestrator_type") == "automation" and request.agent_id:
        return request.agent_id
    return str(config.get("target_agent_id") or "").strip()
