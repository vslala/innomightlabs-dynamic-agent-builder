"""Lead forms in blueprints, so Ila can build a form, the agent that collects it and what happens to each lead."""

from dataclasses import dataclass
from typing import Any, ClassVar, Mapping, Optional

from pydantic import ValidationError

from src.accounts.owner import Owner
from src.blueprints.commands import Command, Reversibility, Undo, Use, undo_action
from src.blueprints.issues import BlueprintIssue
from src.blueprints.kinds.base import (
    Action,
    AppliedResource,
    ApplyContext,
    Change,
    Existing,
    Found,
    ManagedKind,
    NotFound,
    PlanContext,
    Usage,
    one_line,
)
from src.blueprints.reconcile import Outcome
from src.blueprints.spec import LeadFormSpec, lead_form_resource, lead_form_slug
from src.leads.errors import LeadsError
from src.leads.models import CreateLeadFormRequest, LeadForm, LeadFormFields
from src.leads.service import LeadsService


def _applied(name: str, form: LeadForm) -> AppliedResource:
    return AppliedResource(
        name=name,
        kind="LeadForm",
        id=form.form_id,
        attributes={"id": form.form_id, "slug": form.slug, "macro": f"{{{{ lead_form:{form.slug} }}}}"},
    )


def _fields(spec: LeadFormSpec) -> LeadFormFields:
    return LeadFormFields(name=spec.name, purpose=spec.purpose, form_inputs=spec.form_inputs)


# --- Commands -----------------------------------------------------------------------------------------------


@dataclass(kw_only=True)
class CreateLeadForm(Command):
    spec: LeadFormSpec
    #: Known when it's prepared, so the undo can find it even if the apply stops before the create returns.
    slug: str

    reversibility: ClassVar[Reversibility] = Reversibility.COMPENSATABLE
    establishes: ClassVar[bool] = True
    creates: ClassVar[bool] = True

    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        return Undo("delete_lead_form", {"slug": self.slug})

    def run(self, ctx: ApplyContext) -> None:
        request = CreateLeadFormRequest(slug=self.slug, **_fields(self.spec).model_dump())
        form = LeadsService().create_form(ctx.owner.account_id, ctx.owner.user_id, request)
        ctx.applied[self.resource] = _applied(self.resource, form)


@undo_action("delete_lead_form")
def _delete_lead_form(args: dict[str, Any], owner: Owner) -> None:
    leads = LeadsService()
    form = leads.repository.find_form_by_slug(owner.account_id, args["slug"])
    if form is not None:
        leads.delete_form(owner.account_id, form.form_id)


@dataclass(kw_only=True)
class SaveLeadForm(Command):
    form_id: str
    spec: LeadFormSpec

    establishes: ClassVar[bool] = True

    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        current = LeadsService().get_form(ctx.owner.account_id, self.form_id)
        before = LeadFormFields(name=current.name, purpose=current.purpose, form_inputs=current.form_inputs)
        return Undo("restore_lead_form", {"form_id": self.form_id, "fields": before.model_dump(mode="json")})

    def run(self, ctx: ApplyContext) -> None:
        form = LeadsService().update_form(ctx.owner.account_id, self.form_id, _fields(self.spec))
        ctx.applied[self.resource] = _applied(self.resource, form)


@undo_action("restore_lead_form")
def _restore_lead_form(args: dict[str, Any], owner: Owner) -> None:
    """Back to how it was, as a new version: captures already made keep the version they were made with."""
    LeadsService().update_form(owner.account_id, args["form_id"], LeadFormFields.model_validate(args["fields"]))


@dataclass(kw_only=True)
class RemoveLeadForm(Command):
    """Deleted while nothing refers to it; with leads, archived, so they keep the form they came in on."""

    form_id: str

    reversibility: ClassVar[Reversibility] = Reversibility.IRREVERSIBLE
    deletes: ClassVar[bool] = True

    def run(self, ctx: ApplyContext) -> None:
        leads = LeadsService()
        try:
            leads.delete_form(ctx.owner.account_id, self.form_id)
        except LeadsError as refused:
            if refused.code != "FORM_HAS_CAPTURES":
                raise
            leads.archive_form(ctx.owner.account_id, self.form_id)


def missing_lead_forms(slugs: list[str], path: str, ctx: PlanContext) -> list[BlueprintIssue]:
    """Forms named by `slugs` that are neither in this blueprint (planned before whatever names them) nor in the
    account."""
    planned = set(ctx.matched) | ctx.created
    repository = LeadsService().repository
    return [
        BlueprintIssue(
            path=path,
            message=f"There's no lead form '{slug}' in this blueprint or your account.",
            hint=f"Add a LeadForm resource named {lead_form_resource(slug)}, or fix the slug.",
        )
        for slug in slugs
        if lead_form_resource(slug) not in planned and repository.find_form_by_slug(ctx.owner.account_id, slug) is None
    ]


# --- The kind -----------------------------------------------------------------------------------------------


def _found(form: LeadForm) -> Found:
    """Forms are named by slug, so its blueprint resource name and macro are facts worth saying."""
    return Found(
        id=form.form_id,
        name=form.name,
        summary=f"{one_line(form.purpose) or 'A lead form'} ({form.status}, {form.capture_count} leads)",
        record=form,
        facts=(
            f"Slug: `{form.slug}`. Its resource name in a blueprint is `{lead_form_resource(form.slug)}`.",
            f"An agent collects it with `{{{{ lead_form:{form.slug} }}}}` in its instructions.",
            f"Status: {form.status}. Version {form.version}. {form.capture_count} leads.",
        ),
    )


class LeadFormKind(ManagedKind[LeadFormSpec]):
    kind = "LeadForm"
    label = "Lead form"
    use_when = "Capture leads or any details from the people an agent talks to: a demo request, a quote, a claim."
    deletes = "agents stop collecting it; a form that already has leads is archived instead, keeping them"
    spec_model = LeadFormSpec
    exposes = ("id", "slug", "macro")
    feeds = "collected by"
    dashboard_path = "/dashboard/leads/forms/{id}"
    export_name = "lead_form"

    def existing(self, owner: Owner) -> list[Found]:
        return [_found(form) for form in LeadsService().list_forms(owner.account_id)]

    def read(self, owner: Owner, resource_id: str) -> Optional[Found]:
        form = LeadsService().repository.find_form(owner.account_id, resource_id)
        return _found(form) if form else None

    def draft_name(self, record: LeadForm) -> str:
        """A form's slug comes from its resource name, so the name must be the one its slug was made from."""
        return lead_form_resource(record.slug)

    def observe(self, record: LeadForm, names: Mapping[str, str]) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": record.form_id,
            "name": record.name,
            "purpose": record.purpose,
            "form_inputs": [form_input.model_dump(mode="json", exclude_none=True) for form_input in record.form_inputs],
        }

    def applied(self, name: str, record: LeadForm) -> AppliedResource:
        return _applied(name, record)

    def card_details(self, spec: LeadFormSpec) -> list[str]:
        return ["Asks for " + ", ".join(form_input.label for form_input in spec.form_inputs)]

    def page_sections(self) -> list[str]:
        return [
            "### Using it in an agent\n\n"
            "Put `{{ lead_form:<slug> }}` in the agent's `instructions`, where the slug is the resource's name with "
            "hyphens, and give the agent the `lead_capture` skill. The agent then gathers the fields over the "
            "conversation, remembers what it learns, and saves the lead with `capture_lead` once it has every "
            "required field. A form already in the account can be named by its slug too.",
        ]

    def validate(self, name: str, spec: LeadFormSpec) -> list[BlueprintIssue]:
        """What the Leads module would refuse: fields visitors can't be shown, a name that makes no slug."""
        issues = []
        try:
            CreateLeadFormRequest(slug=lead_form_slug(name), **_fields(spec).model_dump())
        except ValidationError as invalid:
            for error in invalid.errors():
                location = ".".join(str(part) for part in error["loc"])
                path = f"resources.{name}" if location == "slug" else f"resources.{name}.{location}"
                issues.append(BlueprintIssue(path=path, message=str(error["msg"]).removeprefix("Value error, ")))
        return issues

    def find_existing(self, name: str, spec: LeadFormSpec, ctx: PlanContext) -> Optional[Existing]:
        repository = LeadsService().repository
        if spec.id:
            form = repository.find_form(ctx.owner.account_id, spec.id)
            if form is None:
                raise NotFound(f"There's no lead form with id '{spec.id}' in your account.")
            return Existing(id=form.form_id, record=form, matched_by="id")
        form = repository.find_form_by_slug(ctx.owner.account_id, lead_form_slug(name))
        return Existing(id=form.form_id, record=form, matched_by="name") if form else None

    def commands(
        self, name: str, spec: LeadFormSpec, existing: Optional[Existing], outcome: Outcome, ctx: PlanContext
    ) -> list[Command]:
        if existing is None:
            return [CreateLeadForm(resource=name, spec=spec, slug=lead_form_slug(name))]
        if not outcome.values(LeadFormSpec):
            return [Use(resource=name, applied=_applied(name, existing.record))]
        return [SaveLeadForm(resource=name, form_id=existing.id, spec=spec, says=outcome.says())]

    def check(self, name: str, spec: LeadFormSpec, change: Change, ctx: PlanContext) -> list[BlueprintIssue]:
        if change.action == Action.CREATE or not change.existing or change.existing.record.is_active:
            return []
        return [BlueprintIssue(
            path=f"resources.{name}",
            message=f"The lead form '{lead_form_slug(name)}' is archived, so agents won't collect it.",
            hint="Restore it under Leads > Forms, or give this form another name.",
        )]

    def usage(self, spec: LeadFormSpec, change: Change) -> Usage:
        return Usage(lead_forms=1 if change.action == Action.CREATE else 0)

    def delete_commands(self, name: str, spec: LeadFormSpec, existing: Existing, removal: str) -> list[Command]:
        return [RemoveLeadForm(resource=name, form_id=existing.id, removal=removal)]

    def describe(self, name: str, spec: LeadFormSpec) -> str:
        return f"Create the lead form '{spec.name}' ({lead_form_slug(name)}) asking for {len(spec.form_inputs)} fields"
