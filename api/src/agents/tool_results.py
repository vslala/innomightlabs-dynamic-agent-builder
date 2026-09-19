"""Side-channel payloads a tool result can carry.

Most tool results are just text for the model. A few are structured payloads
that also mean something to the UI or to the turn's persisted output: a form to
render, a canvas artifact to attach, a credential prompt to surface. Each of
those is one interpreter here, so adding the next one is a new class rather
than another branch in the architecture's event loop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from src.config import settings
from src.llm.events import SSEEvent, SSEEventType
from src.messages.models import MessageCanvasArtifact


@dataclass(frozen=True)
class InterpretedToolResult:
    """What one recognised payload contributes to the turn."""

    event: SSEEvent | None = None
    canvas: MessageCanvasArtifact | None = None
    #: Used as the assistant's reply when the model itself produced no text.
    fallback_text: str | None = None


class ToolResultInterpreter(Protocol):
    def interpret(self, payload: dict[str, Any]) -> InterpretedToolResult | None:
        """Return None when this payload is not the kind of thing I handle."""
        ...


class _UiFormRenderPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    form: dict[str, Any] | None = None
    submit_label: str | None = None


class UiFormRender:
    """A skill asking the widget to render a form.

    The widget renders forms only on UI_FORM_RENDER, so this has to become its
    own event rather than staying inside the tool result.
    """

    def interpret(self, payload: dict[str, Any]) -> InterpretedToolResult | None:
        if payload.get("type") != "ui_form_render":
            return None

        parsed = _UiFormRenderPayload.model_validate(payload)
        form = parsed.form or {}
        label = form.get("form_name") if isinstance(form.get("form_name"), str) else None
        form_id = form.get("form_id") if isinstance(form.get("form_id"), str) else None

        return InterpretedToolResult(
            event=SSEEvent(
                event_type=SSEEventType.UI_FORM_RENDER,
                content=label or "Form",
                form=parsed.form,
                submit_label=parsed.submit_label,
                form_id=form_id,
                form_label=label,
            )
        )


class _CanvasArtifactPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    artifact_id: str
    title: str = "Canvas"
    mime_type: str = "text/html"
    caption: str | None = None


class CanvasArtifact:
    """An agent-authored interactive artifact, attached to the assistant message."""

    def interpret(self, payload: dict[str, Any]) -> InterpretedToolResult | None:
        if payload.get("type") != "canvas_artifact" or not payload.get("ok"):
            return None

        parsed = _CanvasArtifactPayload.model_validate(payload)
        canvas = MessageCanvasArtifact(
            artifact_id=parsed.artifact_id,
            title=parsed.title,
            mime_type=parsed.mime_type,
            caption=parsed.caption,
        )
        base_url = settings.api_base_url.rstrip("/")

        return InterpretedToolResult(
            canvas=canvas,
            event=SSEEvent(
                event_type=SSEEventType.CANVAS_ARTIFACT_READY,
                content=canvas.title,
                canvas_artifact_id=canvas.artifact_id,
                canvas_title=canvas.title,
                canvas_caption=canvas.caption,
                canvas_mime_type=canvas.mime_type,
                canvas_content_url=f"{base_url}/artifacts/{canvas.artifact_id}/content",
            ),
        )


class AuthRequiredCredential:
    """A remote agent refusing until the user adds a credential.

    Produces no event: it only supplies wording for the case where the model
    ends the turn without saying anything itself.
    """

    def interpret(self, payload: dict[str, Any]) -> InterpretedToolResult | None:
        if payload.get("auth_required") is not True:
            return None

        setup_url = payload.get("credential_setup_url")
        if not isinstance(setup_url, str) or not setup_url.strip():
            return None

        agent_name = payload.get("agent_name")
        label = (
            agent_name.strip()
            if isinstance(agent_name, str) and agent_name.strip()
            else "the remote agent"
        )
        return InterpretedToolResult(
            fallback_text=(
                f"{label} requires credentials before I can continue. "
                f"Add the credential here: {setup_url.strip()} "
                "Then retry the request."
            )
        )


#: Order is not significant -- every interpreter that recognises the payload
#: contributes. A result can legitimately match more than one.
INTERPRETERS: list[ToolResultInterpreter] = [
    UiFormRender(),
    CanvasArtifact(),
    AuthRequiredCredential(),
]


def interpret_tool_result(result: str) -> list[InterpretedToolResult]:
    """Everything the interpreters recognise in one tool result."""
    payload = _json_object(result)
    if payload is None:
        return []
    return [
        interpreted
        for interpreted in (i.interpret(payload) for i in INTERPRETERS)
        if interpreted is not None
    ]


def _json_object(result: str) -> dict[str, Any] | None:
    if not isinstance(result, str):
        return None
    try:
        payload = json.loads(result)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None
