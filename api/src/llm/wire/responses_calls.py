"""Whole function calls from a Responses stream, whichever of its events carry the arguments.

A function call streams as several events: the item is added, its arguments arrive as deltas, the arguments are done,
the item is done, and the finished response lists it again. Vendors that speak the API don't all fill in every one:
a single call from xAI streamed its arguments as deltas, while a batch of four arrived with none we read. So a call
is assembled from all of them, and its arguments come from the most authoritative source that has them:

1. the finished item (`response.output_item.done`, or the item in the completed response's `output`);
2. the arguments' own `response.function_call_arguments.done`;
3. the deltas, joined.

A call is emitted once: when its item is done, or, for a vendor that never says so, from the completed response.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.llm.chat import LLMEvent

log = logging.getLogger(__name__)


@dataclass
class _Call:
    call_id: str
    name: str
    deltas: list[str] = field(default_factory=list)
    #: The whole string from the arguments' own `.done` event.
    done_arguments: str = ""
    emitted: bool = False

    def arguments_from(self, item: dict[str, Any] | None) -> tuple[str, str]:
        """(the arguments, where they came from), by authority; ("", "none") when no event carried any."""
        sources = (
            ("item", str((item or {}).get("arguments") or "")),
            ("arguments.done", self.done_arguments),
            ("deltas", "".join(self.deltas)),
        )
        return next(((arguments, source) for source, arguments in sources if arguments), ("", "none"))


class FunctionCallAssembler:
    """The function calls of one streamed response. `label` names the vendor in the logs."""

    def __init__(self, label: str) -> None:
        self.label = label
        self._by_item: dict[str, _Call] = {}
        self._by_index: dict[int, _Call] = {}

    # The three handlers below only record; like `item_done`, they return the events to emit: none.
    def added(self, event: dict[str, Any]) -> list[LLMEvent]:
        item = event.get("item") or {}
        if item.get("type") == "function_call":
            self._register(item, event.get("output_index"))
        return []

    def arguments_delta(self, event: dict[str, Any]) -> list[LLMEvent]:
        if call := self._call_for(event.get("item_id"), event.get("output_index")):
            call.deltas.append(str(event.get("delta") or ""))
        return []

    def arguments_done(self, event: dict[str, Any]) -> list[LLMEvent]:
        if call := self._call_for(event.get("item_id"), event.get("output_index")):
            call.done_arguments = str(event.get("arguments") or "")
        return []

    def item_done(self, event: dict[str, Any]) -> list[LLMEvent]:
        """The call, now that its item is finished; nothing for any other kind of item."""
        item = event.get("item") or {}
        if item.get("type") != "function_call":
            return []
        index = event.get("output_index")
        return self._emit(self._call_for(item.get("id"), index) or self._register(item, index), item)

    def remaining(self, output: object) -> list[LLMEvent]:
        """The calls no `output_item.done` closed: those the completed response lists, in its order, then any others."""
        events: list[LLMEvent] = []
        for index, item in enumerate(output if isinstance(output, list) else []):
            if isinstance(item, dict) and item.get("type") == "function_call":
                events += self._emit(self._call_for(item.get("id"), index) or self._register(item, index), item)
        for call in [*self._by_item.values(), *self._by_index.values()]:
            events += self._emit(call, None)
        return events

    def _emit(self, call: _Call, item: dict[str, Any] | None) -> list[LLMEvent]:
        if call.emitted:
            return []
        call.emitted = True
        arguments, source = call.arguments_from(item)
        # Says which event carried the arguments: a vendor that changes how it streams them shows up here.
        log.info("%s tool call %s %s: arguments from %s (%d chars)", self.label, call.name, call.call_id, source, len(arguments))
        return [LLMEvent.tool_call(call.call_id, call.name, arguments)]

    def _call_for(self, item_id: object, output_index: object) -> _Call | None:
        """The call an event belongs to: by its item id, or by its place in the output when the vendor sends no id."""
        if item_id and str(item_id) in self._by_item:
            return self._by_item[str(item_id)]
        return self._by_index.get(output_index) if isinstance(output_index, int) else None

    def _register(self, item: dict[str, Any], output_index: object) -> _Call:
        """A call, from its item as the vendor first shows it: added, or already finished when it never said so."""
        call = _Call(call_id=str(item.get("call_id") or ""), name=str(item.get("name") or ""))
        if item_id := str(item.get("id") or ""):
            self._by_item[item_id] = call
        if isinstance(output_index, int):
            self._by_index[output_index] = call
        return call
