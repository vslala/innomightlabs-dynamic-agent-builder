"""The tool results consent produces, and the one test for "this result pauses the turn"."""

from __future__ import annotations

import json
from typing import Any

from src.consent.models import ConsentRequest
from src.consent.repository import ConsentRepository

CONSENT_REQUEST = "consent_request"


def consent_request_payload(request: ConsentRequest, repository: ConsentRepository) -> str:
    """What a tool returns when it stops for the person: the card to show, and why the turn stops here."""
    return json.dumps(
        {
            "type": CONSENT_REQUEST,
            "ok": False,
            "status": "waiting_for_approval",
            "message": "Shown to the person to approve. The turn pauses until they decide.",
            "consent": request.to_response(repository.image_url).model_dump(mode="json"),
        },
        ensure_ascii=False,
    )


def is_consent_request(result: str) -> bool:
    """Whether any tool's result asks the person to decide, which pauses the turn."""
    if not isinstance(result, str) or CONSENT_REQUEST not in result:
        return False
    try:
        payload = json.loads(result)
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get("type") == CONSENT_REQUEST


def refusal(reason: str) -> str:
    return json.dumps({"ok": False, "consent": "refused", "reason": reason}, ensure_ascii=False)


def decision_result(request: ConsentRequest) -> str:
    """What the paused call returns once the person has decided: the tool result the resumed turn carries on with."""
    payload: dict[str, Any] = {"consent": "approved" if request.approved else "rejected"}
    if request.approved:
        payload["edited"] = sorted(request.edits)
        payload["always_allowed"] = request.always
        payload["succeeded"] = request.state() == "succeeded"
        payload["result"] = _parsed(request.result)
    elif request.reason:
        payload["reason"] = request.reason
    return json.dumps(payload, ensure_ascii=False)


def _parsed(result: str | None) -> Any:
    if result is None:
        return None
    try:
        return json.loads(result)
    except ValueError:
        return result
