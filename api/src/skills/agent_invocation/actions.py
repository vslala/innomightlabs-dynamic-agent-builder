from __future__ import annotations

from typing import Any

from src.agents.architectures import get_agent_architecture
from src.agents.repository import AgentRepository
from src.conversations.models import AutomationConversation
from src.conversations.repository import ConversationRepository
from src.skills.agent_invocation.models import InvokeAgentRequest


async def invoke(
    arguments: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    del config
    request = InvokeAgentRequest.model_validate(arguments)
    owner_email = str(context.get("owner_email") or "").strip()
    actor_email = str(context.get("actor_email") or owner_email).strip()
    actor_id = str(context.get("actor_id") or actor_email).strip()
    conversation_id = str(context.get("conversation_id") or "").strip()
    if not owner_email:
        raise ValueError("Missing skill runtime owner context")
    if not conversation_id:
        raise ValueError("Missing automation conversation context")

    agent = AgentRepository().find_agent_by_id(request.agent_id, owner_email)
    if not agent:
        raise ValueError("Agent not found")

    conversation = ConversationRepository().find_by_id(conversation_id, owner_email)
    if not isinstance(conversation, AutomationConversation):
        raise ValueError("Automation conversation not found")

    architecture = get_agent_architecture(agent.agent_architecture)
    invocation = await architecture.handle_message_buffered(
        agent=agent,
        conversation=conversation,
        user_message=request.prompt_template,
        owner_email=owner_email,
        actor_email=actor_email,
        actor_id=actor_id,
    )

    if not invocation.success:
        raise ValueError(invocation.error or "Agent invocation failed")

    return {
        "response_text": invocation.response_text,
        "events": [event.model_dump(mode="json", exclude_none=True) for event in invocation.events],
        "message_ids": {
            key: value
            for key, value in {
                "user_message_id": invocation.user_message_id,
                "assistant_message_id": invocation.assistant_message_id,
            }.items()
            if value
        },
    }
