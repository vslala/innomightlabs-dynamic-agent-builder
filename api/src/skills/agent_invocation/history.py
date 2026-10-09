"""The full record of what an invoked agent did, kept for audit when one agent invokes another in a chat.

The calling agent gets only the answer (see `actions.invoke`). Everything the invoked agent did (each tool it
called, with arguments and the whole result) is written to S3 as one JSON document named after the call that
invoked it: `tool_audit_<tool_call_id>.json`. The calling agent's tool-call audit record, saved in DynamoDB next to
its message, has that `tool_call_id`, so each record has exactly one history file and `key_for` finds it.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, cast
from src.artifacts.storage import ArtifactStorage, owner_scope
from src.llm.events import RECORDED_EVENT_TYPES, SSEEvent

log = logging.getLogger(__name__)


def tool_history(events: list[SSEEvent]) -> list[dict[str, Any]]:
    """Every tool call and result, uncapped: this is the audit copy, not something a model reads."""
    return [
        event.model_dump(mode="json", exclude_none=True)
        for event in events
        if event.event_type in RECORDED_EVENT_TYPES
    ]


def key_for(owner_email: str, conversation_id: str, tool_call_id: str) -> str:
    """Where the history of one tool call is kept: the same `tool_call_id` as its audit record."""
    return f"users/{owner_scope(owner_email)}/invocations/{conversation_id}/tool_audit_{tool_call_id}.json"


class InvocationHistoryStore:
    def __init__(self, storage: Optional[ArtifactStorage] = None):
        self._storage = storage

    @property
    def storage(self) -> ArtifactStorage:
        if self._storage is None:
            self._storage = ArtifactStorage()
        return self._storage

    def save(
        self,
        *,
        owner_email: str,
        conversation_id: str,
        tool_call_id: str,
        agent_id: str,
        prompt: str,
        response_text: str,
        events: list[SSEEvent],
        message_ids: dict[str, str],
    ) -> Optional[str]:
        """The S3 key the history was saved under, or None if it couldn't be. Losing the audit copy must never
        cost the person their answer, so a failure is logged, not raised."""
        key = key_for(owner_email, conversation_id, tool_call_id)
        document = {
            "tool_call_id": tool_call_id,
            "invoked_agent_id": agent_id,
            "conversation_id": conversation_id,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "prompt": prompt,
            "response_text": response_text,
            "message_ids": message_ids,
            "tool_calls": tool_history(events),
        }
        try:
            self.storage.put_artifact(
                key=key, body=json.dumps(document, default=str).encode("utf-8"), content_type="application/json"
            )
        except Exception:
            log.warning("Couldn't save the tool history of invoked agent %s", agent_id, exc_info=True)
            return None
        return key

    def load(self, key: str) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.storage.get_object_body(key)))
