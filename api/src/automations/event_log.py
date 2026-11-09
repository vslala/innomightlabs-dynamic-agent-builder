"""What an agent did in one automation step: every tool call and result, whole and in order, kept in S3.

A step's output lands in its own DynamoDB item and again in the run's context, and both share DynamoDB's 400KB
item limit, so a busy agent step can't keep its full tool history there. The runner moves the events out of the
output into one JSON document per step result, and the result keeps only `event_log_key` and `tool_call_count`.
The run inspector loads the log when someone opens the step (`GET .../runs/{run_id}/results/{result_id}/events`).

Runs recorded before this kept capped events inline, at one of `EVENT_HOLDERS`; `inline_events` reads them.

    {member_prefix}/automation-runs/{run_id}/{result_id}.json   {"events": [...]}
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional, cast

from src.accounts.owner import Owner
from src.artifacts.storage import ArtifactStorage, member_prefix
from src.llm.events import SSEEventType

log = logging.getLogger(__name__)

Events = list[dict[str, Any]]


def events_holder(output: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The dict in a step's output that holds the invoked agent's events: the output itself for an agent step, its
    `result` for an invoke-agent skill action. None when the step called no agent."""
    if isinstance(output.get("events"), list):
        return output
    result = output.get("result")
    if isinstance(result, dict) and isinstance(result.get("events"), list):
        return result
    return None


def inline_events(output: dict[str, Any]) -> Events:
    holder = events_holder(output)
    return cast(Events, holder["events"]) if holder else []


def count_tool_calls(events: Events) -> int:
    return sum(1 for event in events if event.get("event_type") == SSEEventType.TOOL_CALL_START.value)


def key_for(owner: Owner, run_id: str, result_id: str) -> str:
    return f"{member_prefix(owner.account_id, owner.user_id)}/automation-runs/{run_id}/{result_id}.json"


class StepEventLogStore:
    def __init__(self, storage: Optional[ArtifactStorage] = None):
        self._storage = storage

    @property
    def storage(self) -> ArtifactStorage:
        if self._storage is None:
            self._storage = ArtifactStorage()
        return self._storage

    def save(self, owner: Owner, run_id: str, result_id: str, events: Events) -> Optional[str]:
        """The key the log was saved under, or None if it couldn't be. A missing log must never fail the run, so a
        failure is logged, not raised."""
        key = key_for(owner, run_id, result_id)
        try:
            self.storage.put_artifact(
                key=key,
                body=json.dumps({"events": events}, default=str).encode("utf-8"),
                content_type="application/json",
            )
        except Exception:
            log.warning("Couldn't save the event log of automation run %s result %s", run_id, result_id, exc_info=True)
            return None
        return key

    def load(self, key: str) -> Events:
        document = json.loads(self.storage.get_object_body(key))
        return cast(Events, document["events"])
