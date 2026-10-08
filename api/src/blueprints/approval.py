"""The person approves a plan before an agent may apply it.

A plan's id is a hash of the exact blueprint and params, and the approval is a form the person
submits in the chat. Apply checks that the latest message from the person approves that id, so an
agent can neither skip the approval nor apply something different from what was approved. The
model can't write a user message, only the person can.
"""

import hashlib
import json
import re
from typing import Any

from src.blueprints.planner import Plan
from src.skills.lead_capture.actions import render_custom_form

APPROVE = "Apply this plan"
REVISE = "Change something"
DECISION_LABEL = "Decision"

_SUBMISSION = re.compile(r'^<form_submission label="([^"]+)">\n([\s\S]*?)\n</form_submission>', re.MULTILINE)


def plan_id_for(yaml: str, params: dict[str, Any]) -> str:
    payload = json.dumps({"yaml": yaml, "params": params}, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def approval_label(plan_id: str) -> str:
    return f"Approve plan {plan_id}"


def approval_form(plan_id: str, plan: Plan, context: dict[str, Any]) -> dict[str, Any]:
    """A `ui_form_render` payload from the Interactive Forms module: the chat shows it under the agent's message."""
    steps = "\n".join(f"{index}. {step.summary}" for index, step in enumerate(plan.steps, start=1))
    return render_custom_form(
        arguments={
            "form_label": approval_label(plan_id),
            "submit_label": "Submit",
            "form_inputs": [{
                "input_type": "choice",
                "name": "decision",
                "label": DECISION_LABEL,
                "values": [APPROVE, REVISE],
                "attr": {"variant": "radio", "help_text": f"This will:\n{steps}"},
            }],
        },
        config={},
        context=context,
    )


def approves(message: str, plan_id: str) -> bool:
    """Whether a chat message is the person approving this plan through its form."""
    match = _SUBMISSION.search(message)
    if not match or match.group(1) != approval_label(plan_id):
        return False
    return any(line.strip() == f"- {DECISION_LABEL}: {APPROVE}" for line in match.group(2).splitlines())
