from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.agents.image_generation.models import GenerateImageRequest
from src.agents.image_generation.service import AgentImageGenerationService
from src.agents.turn_runtime import emit_turn_event, is_droppable_runtime_event
from src.llm.events import SSEEvent, SSEEventType

from .models import GenerateImageActionRequest


def _validate_generate_request(arguments: dict[str, Any]) -> GenerateImageActionRequest:
    try:
        return GenerateImageActionRequest.model_validate(arguments)
    except ValidationError as exc:
        raise ValueError(f"Invalid image generation arguments: {exc}") from exc


async def generate(
    arguments: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    del config

    request = _validate_generate_request(arguments)
    agent_id = str(context.get("agent_id") or "").strip()
    conversation_id = str(context.get("conversation_id") or "").strip()
    owner_email = str(context.get("owner_email") or "").strip()
    actor_email = str(context.get("actor_email") or owner_email).strip()
    user_message_id = str(context.get("user_message_id") or "").strip() or None

    if not agent_id:
        raise ValueError("Image generation requires an agent_id in runtime context")
    if not conversation_id:
        raise ValueError("Image generation requires a conversation_id in runtime context")
    if not owner_email:
        raise ValueError("Image generation requires an owner_email in runtime context")

    service = AgentImageGenerationService()
    final_event: SSEEvent | None = None
    async for event in service.stream_for_agent_turn(
        agent_id=agent_id,
        conversation_id=conversation_id,
        owner_email=owner_email,
        actor_email=actor_email,
        user_message_id=user_message_id,
        request=GenerateImageRequest(
            prompt=request.prompt,
            size=request.size,
            quality=request.quality,
            output_format=request.output_format,
        ),
    ):
        await emit_turn_event(event, droppable=is_droppable_runtime_event(event))
        if event.event_type == SSEEventType.IMAGE_GENERATION_COMPLETE:
            final_event = event

    if final_event is None:
        raise RuntimeError("Image generation completed without a final image event")

    return {
        "type": "generated_image",
        "agent_id": agent_id,
        "conversation_id": conversation_id,
        "user_message_id": user_message_id,
        "assistant_message_id": final_event.message_id,
        "image_count": len(final_event.images or []),
        "images": final_event.images or [],
    }
