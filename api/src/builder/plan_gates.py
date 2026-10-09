"""What `plan_blueprint` tells Ada, decided by a list of gates.

Each gate looks at the attempt and either answers (issues to fix, something to ask the person, blockers, nothing
to change, or the plan to approve) or lets the next one look. The first answer is the tool's result. The last gate
always answers, so every plan ends somewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional, Protocol

from src.blueprints.approval import approval_form, plan_id_for
from src.blueprints.draft import Draft
from src.blueprints.issues import BlueprintIssue, IssueOwner
from src.blueprints.planner import Plan, plan_blueprint
from src.blueprints.validator import ValidatedBlueprint
from src.builder.canvas import drawing_for, save_blueprint_canvas
from src.builder.models import BuilderSession
from src.builder.requirements import Requirement

if TYPE_CHECKING:
    from src.agents.runtime_state import AgentTurnState
    from src.builder.tools import BuilderTools


@dataclass
class PlanAttempt:
    tools: "BuilderTools"
    session: BuilderSession
    state: "AgentTurnState"
    draft: Draft
    params: dict[str, Any]
    #: None when the draft didn't validate; `issues` says why.
    validated: Optional[ValidatedBlueprint]
    issues: list[BlueprintIssue]
    #: What each requirement still needs from the person, in the order they're asked.
    needs: list[tuple[Requirement, list[Any]]]
    _plan: Optional[Plan] = field(default=None, repr=False)

    @property
    def author_issues(self) -> list[BlueprintIssue]:
        """Issues Ada fixes. The person's settings aren't hers: the system asks for them."""
        return [issue for issue in self.issues if issue.owner == IssueOwner.AUTHOR]

    @property
    def needs_person(self) -> bool:
        return any(missing for _, missing in self.needs)

    @property
    def plan(self) -> Plan:
        assert self.validated is not None
        if self._plan is None:
            self._plan = plan_blueprint(self.validated, self.state.owner_email)
        return self._plan

    @property
    def context(self) -> dict[str, Any]:
        return {"agent_id": self.state.agent_id, "conversation_id": self.state.conversation_id}


class PlanGate(Protocol):
    def check(self, attempt: PlanAttempt) -> Optional[dict[str, Any]]: ...


class AuthorIssues:
    """Ada fixes her own issues before the person is asked anything."""

    def check(self, attempt: PlanAttempt) -> Optional[dict[str, Any]]:
        issues = attempt.author_issues or ([] if attempt.needs_person else attempt.issues)
        if not issues:
            return None
        return {
            "ok": False,
            "issues": attempt.tools.pointing_at_pages(attempt.session, issues, attempt.draft),
            "next": (
                "Fix every issue in the YAML and call plan_blueprint again. Each issue's `page` is now open in "
                "your prompt. Don't show these to the person."
            ),
        }


class NeedsPerson:
    """The first thing still needed from the person: an account to connect, then a skill's settings."""

    def check(self, attempt: PlanAttempt) -> Optional[dict[str, Any]]:
        for requirement, missing in attempt.needs:
            if missing:
                return requirement.ask(missing, attempt.session, attempt.state)
        return None


class Blocked:
    def check(self, attempt: PlanAttempt) -> Optional[dict[str, Any]]:
        if attempt.plan.ok:
            return None
        return {
            "ok": False,
            "steps": _steps(attempt.plan),
            "blockers": attempt.tools.pointing_at_pages(attempt.session, attempt.plan.blockers, attempt.draft),
            "next": "Explain what blocks this in plain words and how to fix it, or change the draft and plan again.",
        }


class NothingToChange:
    def check(self, attempt: PlanAttempt) -> Optional[dict[str, Any]]:
        if attempt.plan.changes_anything:
            return None
        return {
            "ok": True,
            "nothing_to_change": True,
            "steps": _steps(attempt.plan),
            "next": "Everything already matches this draft. Tell the person there's nothing to change; don't ask them to approve.",
        }


class AwaitApproval:
    """The plan, with its drawing and the approval form. Nothing is built until the person approves it."""

    def check(self, attempt: PlanAttempt) -> Optional[dict[str, Any]]:
        plan, session = attempt.plan, attempt.session
        assert attempt.validated is not None
        session.plan_id = plan_id_for(attempt.draft.text, attempt.params)
        canvas = save_blueprint_canvas(
            drawing_for(attempt.validated, plan, stage="plan", plan_id=session.plan_id), attempt.state
        )
        return {
            **approval_form(session.plan_id, plan, attempt.context),
            **({"canvas": canvas} if canvas else {}),
            "ok": True,
            "plan_id": session.plan_id,
            "steps": _steps(plan),
            **({"removals": plan.removals} if plan.removals else {}),
            "next": (
                "The person can see the blueprint drawing (with the steps and the YAML) and the approval form "
                "under your message. Describe what you'll build in two or three plain sentences; don't repeat "
                "the steps. Nothing is built until they choose 'Apply this plan'."
                + (" This plan also removes things, which can't be undone: name each one plainly so they know "
                   "before they approve." if plan.removals else "")
            ),
        }


def _steps(plan: Plan) -> list[dict[str, Any]]:
    return [step.model_dump() for step in plan.steps]


PLAN_GATES: tuple[PlanGate, ...] = (AuthorIssues(), NeedsPerson(), Blocked(), NothingToChange(), AwaitApproval())
