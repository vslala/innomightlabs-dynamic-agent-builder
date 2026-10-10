"""Kits: everything one blueprint built, kept together so it can be changed, rolled back or removed as one.

A kit is the lasting boundary, and each apply is a version of it:

- **Identity.** The kit maps each blueprint name to the resource it is (`Kit.resources`). That map is pinned into
  every plan, so a name always means the same agent or knowledge base, whatever the YAML says.
- **Desired state.** A version's blueprint is the whole of what the kit should hold. The next plan compares it with
  the last applied version (`before`): what that declared and this leaves out is removed; what the kit never
  declared is never touched.
- **Rolling back** to a version is planning that version's blueprint against the kit as it is now.
- **Removing** a kit is planning nothing against it.

Both go through a plan the person sees first. Its `plan_id` says exactly what they saw, so the apply that follows
can't do anything else.

DynamoDB: pk=User#{owner_email}, sk=Kit#{kit_id}. Versions are deployments with `kit_id` (`BlueprintDeployment#…`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from boto3.dynamodb.conditions import Key
from pydantic import BaseModel, Field

from src.blueprints.approval import plan_id_for
from src.blueprints.draft import Draft
from src.blueprints.issues import BlueprintInvalid
from src.blueprints.models import Deployment, DeploymentAction, DeploymentStatus, JournalState
from src.blueprints.planner import Plan, plan_blueprint, plan_removal
from src.blueprints.repository import DeploymentRepository
from src.blueprints.validator import ValidatedBlueprint, validate_blueprint
from src.config import settings
from src.db import get_dynamodb_resource
from src.utils.dynamodb import convert_decimals, convert_floats_to_decimals

SK_PREFIX = "Kit#"


class KitStatus(str, Enum):
    ACTIVE = "active"
    #: Everything it held was deleted; its history stays.
    REMOVED = "removed"


class KitResource(BaseModel):
    kind: str
    id: str


class Kit(BaseModel):
    kit_id: str = Field(default_factory=lambda: str(uuid4()))
    owner_email: str
    #: From the blueprint's metadata.
    name: str
    title: str
    description: Optional[str] = None
    status: KitStatus = KitStatus.ACTIVE
    #: What the kit holds now, by blueprint name: its identity.
    resources: dict[str, KitResource] = Field(default_factory=dict)
    #: The last version applied in full. Its blueprint is what the kit declares now, and the next plan's `before`.
    current_deployment_id: Optional[str] = None
    current_version: int = 0
    #: How many versions it has, counting ones that only partly applied.
    versions: int = 0
    #: The conversation with Ila it was built in, if any.
    conversation_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def ids(self) -> dict[str, str]:
        return {name: resource.id for name, resource in self.resources.items()}


class KitRepository:
    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def save(self, kit: Kit) -> Kit:
        kit.updated_at = datetime.now(timezone.utc)
        item = {"pk": f"User#{kit.owner_email}", "sk": f"{SK_PREFIX}{kit.kit_id}", "entity_type": "Kit",
                **kit.model_dump(mode="json")}
        self.table.put_item(Item=convert_floats_to_decimals(item))
        return kit

    def find(self, owner_email: str, kit_id: str) -> Optional[Kit]:
        item = self.table.get_item(Key={"pk": f"User#{owner_email}", "sk": f"{SK_PREFIX}{kit_id}"}).get("Item")
        return self._from_item(item) if item else None

    def list_by_user(self, owner_email: str) -> list[Kit]:
        """Most recently changed first."""
        kwargs: dict = {"KeyConditionExpression": Key("pk").eq(f"User#{owner_email}") & Key("sk").begins_with(SK_PREFIX)}
        kits = []
        while True:
            response = self.table.query(**kwargs)
            kits += [self._from_item(item) for item in response.get("Items", [])]
            if "LastEvaluatedKey" not in response:
                break
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        return sorted(kits, key=lambda kit: kit.updated_at or kit.created_at, reverse=True)

    def holding(self, owner_email: str, resource_id: str) -> Optional[Kit]:
        """The active kit a resource belongs to. A resource is in at most one."""
        return next(
            (kit for kit in self.list_by_user(owner_email)
             if kit.status == KitStatus.ACTIVE and any(r.id == resource_id for r in kit.resources.values())),
            None,
        )

    @staticmethod
    def _from_item(item: dict) -> Kit:
        return Kit.model_validate(convert_decimals({k: v for k, v in item.items() if k not in ("pk", "sk", "entity_type")}))


# --- Planning against a kit ---------------------------------------------------------------------------------


class KitError(Exception):
    """The kit can't be used as asked: it's been removed, or it has no such version."""


class KitNotFound(KitError):
    """There's no kit with that id in the person's account."""


@dataclass(frozen=True)
class KitPlan:
    """A plan the person sees before anything happens. `plan_id` says exactly what it is."""

    validated: ValidatedBlueprint
    plan: Plan
    plan_id: str
    action: DeploymentAction
    #: For a rollback, the version it goes back to.
    version: Optional[int] = None


def pin(text: str, kit: Optional[Kit]) -> str:
    """The blueprint with every name the kit knows pinned to the resource it is."""
    return Draft(text).pinned(kit.ids).text if kit else text


def declared(kit: Optional[Kit], baseline: Optional[str] = None) -> Optional[ValidatedBlueprint]:
    """What the kit declares now (its last version applied in full), with its ids pinned: the `before` of its next
    plan. For something that isn't in a kit yet, `baseline` (what it was when it was loaded) stands in."""
    if kit is not None and kit.current_deployment_id:
        deployment = DeploymentRepository().find_by_id(kit.owner_email, kit.current_deployment_id)
        if deployment is None:
            raise KitError("The kit's last version can't be found.")
        return _validated(pin(Draft(deployment.blueprint_yaml).without_ids().text, kit), deployment.params)
    if baseline:
        return _validated(baseline, {})
    return None


def _validated(text: str, params: dict[str, Any]) -> ValidatedBlueprint:
    try:
        return validate_blueprint(text, params)
    except BlueprintInvalid as e:
        # A skill manifest may have changed since; the kit can't know what it declared.
        raise KitError("The kit's last version doesn't read any more: " + "; ".join(i.message for i in e.issues)) from e


def active_kit(owner_email: str, kit_id: str) -> Kit:
    kit = KitRepository().find(owner_email, kit_id)
    if kit is None:
        raise KitNotFound("There's no such kit.")
    if kit.status != KitStatus.ACTIVE:
        raise KitError("This kit has been removed.")
    return kit


def plan_rollback(owner_email: str, kit_id: str, version: int) -> KitPlan:
    kit = active_kit(owner_email, kit_id)
    target = next((d for d in DeploymentRepository().list_for_kit(owner_email, kit_id) if d.version == version), None)
    if target is None or target.status == DeploymentStatus.FAILED:
        raise KitError(f"The kit has no version {version}.")
    if target.action == DeploymentAction.REMOVE:
        raise KitError("That version removed the kit; there's nothing to go back to.")
    text = pin(Draft(target.blueprint_yaml).without_ids().text, kit)
    validated = _validated(text, target.params)
    plan = plan_blueprint(validated, owner_email, declared(kit))
    return KitPlan(validated, plan, _plan_id("rollback", kit, text, target.params), DeploymentAction.ROLLBACK, version)


def plan_kit_removal(owner_email: str, kit_id: str) -> KitPlan:
    kit = active_kit(owner_email, kit_id)
    before = declared(kit)
    if before is None:
        raise KitError("The kit has no version to remove.")
    plan = plan_removal(before, owner_email)
    # What's recorded for the removal: the version it removed, with no outputs to show.
    validated = ValidatedBlueprint(
        blueprint=before.blueprint.model_copy(update={"outputs": {}}), yaml=before.yaml, params=before.params, order=[]
    )
    return KitPlan(validated, plan, _plan_id("remove", kit, before.yaml, before.params), DeploymentAction.REMOVE)


def _plan_id(action: str, kit: Kit, text: str, params: dict[str, Any]) -> str:
    """Changes when the kit does, so a plan seen before another version was applied can't be applied after it."""
    return plan_id_for(f"{action}:{kit.kit_id}:{kit.versions}\n{text}", params)


# --- Recording a version --------------------------------------------------------------------------------------


def record_version(
    kit: Optional[Kit], deployment: Deployment, planned: KitPlan, conversation_id: Optional[str] = None
) -> Optional[Kit]:
    """The kit after this deployment. One that changed nothing (it failed and was put back, or there was nothing to
    do) isn't a version."""
    if deployment.status == DeploymentStatus.FAILED:
        return kit
    if kit is not None and not planned.plan.changes_anything:
        # Nothing changed, but a resource may be known by a new name now.
        kit.resources = {name: KitResource(kind=r.kind, id=r.id) for name, r in deployment.resources.items()}
        return KitRepository().save(kit)
    metadata = planned.validated.blueprint.metadata
    kit = kit or Kit(owner_email=deployment.user_email, name=metadata.name, title=metadata.title,
                     conversation_id=conversation_id)
    kit.versions += 1
    deployment.kit_id, deployment.version = kit.kit_id, kit.versions
    DeploymentRepository().save(deployment)

    deleted = {entry.resource for entry in deployment.journal if entry.deletes and entry.state == JournalState.DONE}
    held = {name: KitResource(kind=r.kind, id=r.id) for name, r in deployment.resources.items()}
    if deployment.status == DeploymentStatus.APPLIED:
        kit.resources = held
        kit.current_deployment_id, kit.current_version = deployment.deployment_id, kit.versions
        if planned.action != DeploymentAction.REMOVE:
            kit.name, kit.title, kit.description = metadata.name, metadata.title, metadata.description
    else:
        # Part-way: it holds what it held and what was built, less what was deleted. Its declared state stays the
        # last full version, so applying again retries what didn't finish.
        kit.resources = {name: r for name, r in {**kit.resources, **held}.items() if name not in deleted}
    if planned.action == DeploymentAction.REMOVE and deployment.status == DeploymentStatus.APPLIED:
        kit.status, kit.resources = KitStatus.REMOVED, {}
    return KitRepository().save(kit)
