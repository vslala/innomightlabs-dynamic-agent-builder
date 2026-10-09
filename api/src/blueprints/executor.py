"""Applying a planned blueprint: run its commands in order, each one's undo saved on the deployment before it runs.

Everything that can be undone runs first. If one of those fails, the saved undos are run, newest first, and the
account is as it was. Then comes the commit point, and after it what can't be undone (deleting, reading a site).
If one of those fails, everything before it stays applied and the deployment says what's left; applying the same
blueprint again finishes the job, since what's already done is planned as done.

An apply the process didn't finish (a restart part-way) is found by `recover_interrupted` and put back the same
way, from its saved undos.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import BackgroundTasks

from src.blueprints.commands import COMMIT, Command, Undo, run_undo
from src.blueprints.kinds import AppliedResource, ApplyContext
from src.blueprints.models import (
    DeployedResource,
    Deployment,
    DeploymentOutput,
    DeploymentStatus,
    JournalEntry,
    JournalState,
    UndoRecord,
)
from src.blueprints.planner import Plan
from src.blueprints.repository import DeploymentRepository
from src.blueprints.validator import RESOURCE_REF, TEMPLATE, ValidatedBlueprint
from src.config import settings
from src.rate_limits.limiter import RateLimitPolicy

log = logging.getLogger(__name__)


def apply_rate_limit() -> RateLimitPolicy:
    """Blueprint applies per owner per hour, from the dashboard and from agents alike."""
    return RateLimitPolicy.sliding_window("BLUEPRINT_APPLY", limit=settings.blueprint_apply_limit, seconds=3600)


def apply_blueprint(
    validated: ValidatedBlueprint,
    plan: Plan,
    user_email: str,
    background_tasks: BackgroundTasks | None = None,
    repository: DeploymentRepository | None = None,
    deployment_fields: dict[str, Any] | None = None,
) -> Deployment:
    """Call only with a plan that has no blockers. The deployment is saved at every step, so a failure part-way
    still says what was touched, and how to put it back."""
    repository = repository or DeploymentRepository()
    blueprint = validated.blueprint
    deployment = repository.save(Deployment(
        user_email=user_email,
        blueprint_name=blueprint.metadata.name,
        blueprint_title=blueprint.metadata.title,
        blueprint_yaml=validated.yaml,
        params=validated.params,
        steps=[step.summary for step in plan.steps],
        **(deployment_fields or {}),
    ))
    ctx = ApplyContext(user_email=user_email, background_tasks=background_tasks)
    for step in plan.commands:
        if step is COMMIT:
            deployment.committed = True
            repository.save(deployment)
            continue
        assert isinstance(step, Command)
        try:
            _run(step, ctx, deployment, repository)
        except Exception as e:
            log.exception("Blueprint %s failed for %s at %s", blueprint.metadata.name, user_email, step.name)
            reason = str(e) or type(e).__name__
            if deployment.committed:
                deployment.error = f"Everything that could be undone was applied, but this didn't finish: {reason}"
                deployment.status = DeploymentStatus.FAILED_PARTIAL
            else:
                deployment.error = reason
                deployment.status = unwind(deployment)
            return repository.save(deployment)

    deployment.outputs = {
        name: DeploymentOutput(value=_fill_outputs(output.value, ctx.applied), description=output.description)
        for name, output in blueprint.outputs.items()
    }
    deployment.status = DeploymentStatus.APPLIED
    return repository.save(deployment)


def _run(command: Command, ctx: ApplyContext, deployment: Deployment, repository: DeploymentRepository) -> None:
    """Write ahead: the entry, with its undo, is saved before the command runs, then marked done."""
    undo = command.prepare(ctx)
    entry = JournalEntry(
        command=command.name,
        resource=command.resource,
        undo=UndoRecord(action=undo.action, args=undo.args) if undo else None,
        creates=command.creates,
        deletes=command.deletes,
        removal=command.removal,
    )
    deployment.journal.append(entry)
    repository.save(deployment)
    command.run(ctx)
    entry.state = JournalState.DONE
    if command.resource in ctx.applied:
        _record(deployment, ctx.applied[command.resource])
    if command.removal:
        deployment.removed.append(command.removal)
    repository.save(deployment)


def unwind(deployment: Deployment) -> DeploymentStatus:
    """Runs the saved undos, newest first, including the one for a command that may have stopped part-way. Returns
    FAILED when everything was put back, FAILED_PARTIAL when an undo failed too."""
    status = DeploymentStatus.FAILED
    for entry in reversed(deployment.journal):
        if entry.state not in (JournalState.STARTED, JournalState.DONE):
            continue
        try:
            if entry.undo:
                run_undo(Undo(entry.undo.action, entry.undo.args), deployment.user_email)
        except Exception:
            log.exception("Undoing %s failed for deployment %s", entry.command, deployment.deployment_id)
            entry.state = JournalState.UNDO_FAILED
            status = DeploymentStatus.FAILED_PARTIAL
            continue
        entry.state = JournalState.UNDONE
        if entry.creates:
            deployment.resources.pop(entry.resource, None)
        if entry.removal in deployment.removed:
            deployment.removed.remove(entry.removal)
    return status


def recover_interrupted(repository: DeploymentRepository | None = None, *, now: datetime | None = None) -> int:
    """Finishes applies the process stopped part-way through: puts back what it did if it hadn't reached the commit
    point, and otherwise says what's left. Returns how many it found."""
    repository = repository or DeploymentRepository()
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(seconds=settings.blueprint_apply_stale_timeout_seconds)
    stale = repository.list_applying(updated_before=cutoff)
    for deployment in stale:
        if deployment.committed:
            deployment.status = DeploymentStatus.FAILED_PARTIAL
            deployment.error = (
                "The build was interrupted after everything that could be undone was applied. "
                "Apply the same blueprint again to finish it."
            )
        else:
            deployment.status = unwind(deployment)
            deployment.error = "The build was interrupted, so what it had done was put back."
        repository.save(deployment)
    return len(stale)


def _record(deployment: Deployment, applied: AppliedResource) -> None:
    deployment.resources[applied.name] = DeployedResource(
        kind=applied.kind, id=applied.id, attributes=dict(applied.attributes)
    )


def _fill_outputs(text: str, applied: dict[str, AppliedResource]) -> str:
    def fill(match: re.Match[str]) -> str:
        reference = RESOURCE_REF.match(match.group(1))
        if not reference:
            return match.group(0)
        name, attribute = reference.groups()
        return applied[name].attributes.get(attribute, "") if name in applied else ""
    return TEMPLATE.sub(fill, text)
