"""Applying a planned blueprint: create in dependency order, start crawls last, roll back on failure."""

import logging
import re
from datetime import datetime, timezone

from fastapi import BackgroundTasks

from src.blueprints.kinds import AppliedResource, ApplyContext, kind_for
from src.blueprints.models import DeployedResource, Deployment, DeploymentOutput, DeploymentStatus
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
    user_email: str,
    background_tasks: BackgroundTasks | None = None,
    repository: DeploymentRepository | None = None,
) -> Deployment:
    """Call only with a plan that has no blockers. The deployment is recorded at every step, so a
    failure part-way still says what was created."""
    repository = repository or DeploymentRepository()
    blueprint = validated.blueprint
    deployment = repository.save(Deployment(
        user_email=user_email,
        blueprint_name=blueprint.metadata.name,
        blueprint_title=blueprint.metadata.title,
        blueprint_yaml=validated.yaml,
        params=validated.params,
    ))
    ctx = ApplyContext(user_email=user_email, background_tasks=background_tasks)
    created: list[AppliedResource] = []
    try:
        for name in validated.order:
            spec = blueprint.resources[name]
            applied = kind_for(spec.kind).apply(name, spec, ctx)
            ctx.applied[name] = applied
            created.append(applied)
            _record(deployment, applied)
            repository.save(_touch(deployment))
        for applied in created:
            kind_for(applied.kind).start(applied, blueprint.resources[applied.name], ctx)
            _record(deployment, applied)
    except Exception as e:
        log.exception("Blueprint %s failed for %s", blueprint.metadata.name, user_email)
        deployment.error = str(e) or type(e).__name__
        deployment.status = _roll_back(created, ctx, deployment)
        return repository.save(_touch(deployment))

    deployment.outputs = {
        name: DeploymentOutput(value=_fill_outputs(output.value, ctx.applied), description=output.description)
        for name, output in blueprint.outputs.items()
    }
    deployment.status = DeploymentStatus.APPLIED
    return repository.save(_touch(deployment))


def _roll_back(created: list[AppliedResource], ctx: ApplyContext, deployment: Deployment) -> DeploymentStatus:
    status = DeploymentStatus.FAILED
    for applied in reversed(created):
        try:
            kind_for(applied.kind).rollback(applied, ctx)
            deployment.resources.pop(applied.name, None)
        except Exception:
            log.exception("Rollback of %s %s failed", applied.kind, applied.id)
            status = DeploymentStatus.FAILED_PARTIAL
    return status


def _record(deployment: Deployment, applied: AppliedResource) -> None:
    deployment.resources[applied.name] = DeployedResource(
        kind=applied.kind, id=applied.id, attributes=dict(applied.attributes)
    )


def _touch(deployment: Deployment) -> Deployment:
    deployment.updated_at = datetime.now(timezone.utc)
    return deployment


def _fill_outputs(text: str, applied: dict[str, AppliedResource]) -> str:
    def fill(match: re.Match[str]) -> str:
        reference = RESOURCE_REF.match(match.group(1))
        if not reference:
            return match.group(0)
        name, attribute = reference.groups()
        return applied[name].attributes.get(attribute, "") if name in applied else ""
    return TEMPLATE.sub(fill, text)
