"""Why Leads refused something, in terms every client (and an agent) can act on."""

from __future__ import annotations

from src.exceptions import Refusal


class LeadsError(Refusal):
    """Leads refused something. Rendered by the `Refusal` handler in `src/exceptions.py`; a skill action passes the
    message to the agent, so it says what to do next."""


def form_not_found(slug_or_id: str) -> LeadsError:
    return LeadsError("FORM_NOT_FOUND", f"There is no lead form '{slug_or_id}' in this account.", 404)


def capture_not_found() -> LeadsError:
    return LeadsError("CAPTURE_NOT_FOUND", "Lead not found.", 404)


def plan_limit(message: str) -> LeadsError:
    return LeadsError("PLAN_LIMIT", f"{message} Upgrade your plan for more.", 429)
