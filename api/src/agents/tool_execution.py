"""Tool execution policy: what may run, timeouts, error shape, and prompt staleness.

The registry knows how to run a tool. This decides what happens when it takes
too long or raises, and reports when a tool has invalidated the system prompt.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from src.agents.runtime_state import AgentTurnState
from src.agents.tool_runtime import ToolCategory, ToolExecutionOutcome, ToolRegistry
from src.agents.tool_runtime.current_call import current_consent_grant, current_tool_call_id
from src.consent.payloads import is_consent_request

if TYPE_CHECKING:
    from src.consent.gate import ConsentGate

log = logging.getLogger(__name__)

class ToolExecutionRouter:
    def __init__(self, registry: ToolRegistry, *, offered: set[ToolCategory], consent: "ConsentGate | None" = None):
        self._registry = registry
        #: The categories the turn told the model about: a tool outside them doesn't run, whatever the model asks.
        self._offered = offered
        #: Asked before every call whether it needs the person's consent (docs/LLD-action-consent.md).
        self._consent = consent

    async def execute(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
        state: AgentTurnState,
    ) -> ToolExecutionOutcome:
        """Never raises: a failure is a result the model gets to read and react to."""
        call = current_tool_call_id.set(tool_use_id)
        grant = current_consent_grant.set(None)
        try:
            tool = self._registry.get(tool_name)
            if tool.spec.category not in self._offered:
                return ToolExecutionOutcome(result=f"Error: '{tool_name}' isn't available in this conversation.", success=False)
            if self._consent is not None:
                decision = await self._consent.check(
                    tool_name=tool_name, tool_input=tool_input, tool_use_id=tool_use_id, state=state
                )
                if decision.result is not None:
                    asks = is_consent_request(decision.result)
                    return ToolExecutionOutcome(result=decision.result, success=asks, ends_turn=asks)
                current_consent_grant.set(decision.grant)
            run = tool.run(tool_input, state)
            if tool.spec.timeout_seconds:
                result = await asyncio.wait_for(run, timeout=tool.spec.timeout_seconds)
            else:
                result = await run

            return ToolExecutionOutcome(
                result=result,
                success=True,
                refresh_prompt=tool.spec.mutates_prompt_context,
                # Any tool may stop for the person, not only the gate: Ila's apply raises a card for automation steps
                ends_turn=is_consent_request(result),
            )

        except TimeoutError:
            log.warning(
                "Tool execution timed out: tool=%s tool_use_id=%s", tool_name, tool_use_id
            )
            return ToolExecutionOutcome(
                result=f"Error: Tool '{tool_name}' timed out before completing.",
                success=False,
            )
        except Exception as e:
            log.error(
                "Tool execution error: tool=%s tool_use_id=%s err=%s",
                tool_name,
                tool_use_id,
                e,
                exc_info=True,
            )
            return ToolExecutionOutcome(result=f"Error: {str(e)}", success=False)
        finally:
            current_consent_grant.reset(grant)
            current_tool_call_id.reset(call)


__all__ = ["ToolExecutionOutcome", "ToolExecutionRouter"]
