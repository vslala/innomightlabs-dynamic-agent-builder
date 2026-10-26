"""What a turn accumulates while the loop streams, and the reply it saves at the end.

Shared by the architectures that run the agentic loop (KrishnaMemGPT, Vishwakarma).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterator

from src.agents.agentic_loop import TurnPaused
from src.agents.tool_results import interpret_tool_result
from src.consent.models import TurnCheckpoint
from src.consent.repository import ConsentRepository
from src.llm.events import SSEEvent, SSEEventType
from src.messages.models import Message, MessageCanvasArtifact, MessageConsent
from src.messages.repositories import MessageRepository

#: Why the model gave no summary, in words the user (and the next turn) can act on.
WHY_NO_SUMMARY = {
    "max_tokens": "the model reached its output limit before it could write a summary",
    "content_filter": "the provider's content filter blocked the summary",
}


@dataclass
class TurnOutputs:
    """What the architecture accumulates while the loop streams."""

    full_text: str = ""
    stop_reason: str = "end_turn"
    canvases: list[MessageCanvasArtifact] = field(default_factory=list)
    #: Wording to use when the model itself produced no text.
    fallback_text: str | None = None
    #: How often each tool ran this turn, by the name the user sees.
    tool_runs: Counter[str] = field(default_factory=Counter)
    failed_tool_runs: int = 0
    #: A tool already answered the user on its own -- a generated image, say --
    #: so silence from the model is not a failure.
    answered_without_text: bool = False
    #: Consent cards raised this turn, kept on the reply.
    consents: list[MessageConsent] = field(default_factory=list)
    #: Set when the turn paused for the person's decision.
    paused: TurnPaused | None = None

    def absorb(self, event: SSEEvent) -> Iterator[SSEEvent]:
        """Take what this event contributes, yielding any events it implies."""
        if event.event_type == SSEEventType.IMAGE_GENERATION_COMPLETE:
            self.answered_without_text = True
        elif event.event_type == SSEEventType.TOOL_CALL_RESULT:
            self.tool_runs[event.display_tool_name or event.tool_name or "tool"] += 1
            if event.success is False:
                self.failed_tool_runs += 1
            for interpreted in interpret_tool_result(event.content):
                if interpreted.canvas:
                    self.canvases.append(interpreted.canvas)
                if interpreted.consent:
                    self.consents.append(interpreted.consent)
                self.fallback_text = self.fallback_text or interpreted.fallback_text
                if interpreted.event:
                    yield interpreted.event

    @property
    def assistant_text(self) -> str:
        """What to persist as the assistant's reply, substituting if it said nothing."""
        if self.full_text.strip():
            return self.full_text
        if self.fallback_text:
            return self.fallback_text
        if self.tool_runs and not self.answered_without_text:
            return self.record_of_tool_runs()
        return ""

    def record_of_tool_runs(self) -> str:
        """Saved when the model could not answer, so the next turn still knows what already ran."""
        count = sum(self.tool_runs.values())
        calls = "1 tool call" if count == 1 else f"{count} tool calls"
        runs = ", ".join(name if times == 1 else f"{name} ×{times}" for name, times in self.tool_runs.most_common())
        failed = f"; {self.failed_tool_runs} failed" if self.failed_tool_runs else ""
        why = WHY_NO_SUMMARY.get(self.stop_reason, "I couldn't write a summary of them")
        return (
            f"I ran {calls} ({runs}{failed}), but {why}. "
            "Ask me to summarise what was done; I won't run them again unless you ask."
        )

    def save_reply(
        self,
        message_repo: MessageRepository,
        *,
        conversation_id: str,
        actor_email: str,
        model_name: str,
    ) -> Iterator[SSEEvent]:
        """Save what the assistant said, with its canvases and consent cards, and the checkpoint of a paused turn."""
        assistant_text = self.assistant_text
        if not assistant_text.strip():
            return

        # Substituted text has not been streamed yet; the model's own has.
        if not self.full_text.strip():
            yield SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content=assistant_text)

        reply = Message(
            conversation_id=conversation_id,
            created_by=actor_email,
            role="assistant",
            content=assistant_text,
            # Kept on the message so they survive a reload
            canvases=self.canvases,
            consents=self.consents,
        )
        message_repo.save(reply)
        if self.paused and self.consents:
            self._keep_checkpoint(reply.message_id, model_name)
        yield SSEEvent(
            event_type=SSEEventType.ASSISTANT_MESSAGE_SAVED,
            content="Assistant message saved",
            message_id=reply.message_id,
        )

    def _keep_checkpoint(self, assistant_message_id: str, model_name: str) -> None:
        assert self.paused is not None
        consents = ConsentRepository()
        request = consents.get(self.consents[-1].consent_id)
        if request is None:
            return
        consents.keep_checkpoint(
            request,
            TurnCheckpoint(
                tool_use_id=self.paused.tool_use_id,
                model_name=model_name,
                exchange=self.paused.exchange,
                assistant_message_id=assistant_message_id,
            ),
        )
