"""Leads: forms, the account's statuses, and saving and reading captures. See docs/LLD-lead-capture.md."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel

from src.form_models import FormInput
from src.form_validation import SubmissionResult, validate_submission
from src.leads.errors import LeadsError, capture_not_found, form_not_found, plan_limit
from src.leads.models import (
    SOURCE_BY_ACTOR,
    Answers,
    Capture,
    CaptureFile,
    CaptureFilters,
    CapturePage,
    CaptureSource,
    CreateLeadFormRequest,
    LeadForm,
    LeadFormFields,
    LeadSettings,
    LeadSettingsRequest,
    LabelledAnswer,
    LeadUsage,
    ad_hoc_form,
    capture_id_for,
)
from src.leads.files import LeadFiles
from src.leads.repository import DuplicateCapture, FormHasCaptures, LeadsRepository, SlugTaken
from src.rate_limits.service import RateLimitService
from src.skills.models import ActorKind

MAX_ANSWER_BYTES = 16 * 1024


class CaptureOrigin(BaseModel):
    """Where a capture came from: the agent's run, never the agent's arguments."""

    account_id: str
    agent_id: str
    conversation_id: str | None = None
    actor_kind: ActorKind
    actor_id: str
    actor_email: str | None = None

    @property
    def source(self) -> CaptureSource:
        return SOURCE_BY_ACTOR[self.actor_kind]


@dataclass(frozen=True)
class CaptureResult:
    capture: Capture
    #: The same lead was saved before; nothing new was stored
    duplicate: bool
    #: Past the plan's monthly limit: stored, but hidden until the account upgrades
    locked: bool


class LeadsService:
    def __init__(
        self,
        repository: LeadsRepository | None = None,
        limits: RateLimitService | None = None,
        files: LeadFiles | None = None,
    ) -> None:
        self.repository = repository or LeadsRepository()
        self.limits = limits or RateLimitService()
        self.files = files or LeadFiles(self.repository)

    # Forms

    def list_forms(self, account_id: str) -> list[LeadForm]:
        return self.repository.list_forms(account_id)

    def get_form(self, account_id: str, form_id: str) -> LeadForm:
        form = self.repository.find_form(account_id, form_id)
        if form is None:
            raise form_not_found(form_id)
        return form

    def create_form(self, account_id: str, user_id: str, request: CreateLeadFormRequest) -> LeadForm:
        self._require_form_slot(account_id)
        form = LeadForm(account_id=account_id, created_by=user_id, **request.model_dump())
        try:
            return self.repository.create_form(form)
        except SlugTaken:
            raise LeadsError("SLUG_TAKEN", f"Another lead form already uses the slug '{form.slug}'.", 409) from None

    def update_form(self, account_id: str, form_id: str, fields: LeadFormFields) -> LeadForm:
        return self.repository.update_form(self.get_form(account_id, form_id).revised(fields))

    def archive_form(self, account_id: str, form_id: str) -> LeadForm:
        form = self.get_form(account_id, form_id)
        return self.repository.update_form(form.model_copy(update={"status": "archived", "updated_at": _now()}))

    def restore_form(self, account_id: str, form_id: str) -> LeadForm:
        form = self.get_form(account_id, form_id)
        if form.is_active:
            return form
        self._require_form_slot(account_id)
        return self.repository.update_form(form.model_copy(update={"status": "active", "updated_at": _now()}))

    def delete_form(self, account_id: str, form_id: str) -> None:
        try:
            self.repository.delete_form(self.get_form(account_id, form_id))
        except FormHasCaptures:
            raise LeadsError(
                "FORM_HAS_CAPTURES", "This form has leads, so it can only be archived. Archiving keeps them.", 409
            ) from None

    def _require_form_slot(self, account_id: str) -> None:
        limit = self.limits.get_account_limits(account_id).lead_forms
        active = sum(form.is_active for form in self.repository.list_forms(account_id))
        if limit and active >= limit:
            raise plan_limit(f"Your plan includes {limit} active lead form{'s' if limit != 1 else ''}.")

    # Statuses

    def settings(self, account_id: str) -> LeadSettings:
        return self.repository.find_settings(account_id)

    def update_settings(self, account_id: str, user_id: str, request: LeadSettingsRequest) -> LeadSettings:
        """Removing a status that leads still have needs somewhere to move them, so none is left meaningless."""
        updated = LeadSettings(account_id=account_id, statuses=request.statuses, updated_by=user_id, updated_at=_now())
        for removed in self.settings(account_id).status_keys - updated.status_keys:
            replacement = request.replacements.get(removed)
            if replacement is None:
                if next(self.repository.captures_with_status(account_id, removed), None):
                    raise LeadsError(
                        "STATUS_IN_USE", f"Some leads are '{removed}'. Choose a status to move them to.", 409
                    )
                continue
            if replacement not in updated.status_keys:
                raise LeadsError("UNKNOWN_STATUS", f"'{replacement}' is not one of the new statuses.")
            for capture in self.repository.captures_with_status(account_id, removed):
                self.repository.update_capture_status(capture, replacement)
        return self.repository.save_settings(updated)

    # Captures

    def find_active_form(self, account_id: str, slug: str) -> LeadForm:
        form = self.repository.find_form_by_slug(account_id, slug)
        if form is None:
            raise form_not_found(slug)
        if not form.is_active:
            raise LeadsError("FORM_ARCHIVED", f"The lead form '{slug}' is no longer collecting.")
        return form

    def validate(self, form: LeadForm, answers: Answers) -> SubmissionResult:
        """Answers checked against the form; a name the form doesn't have is an error, so agents can't add fields."""
        result = validate_submission(form.form_inputs, answers)
        known = {form_input.name for form_input in form.form_inputs}
        for name in sorted(set(answers) - known):
            result.invalid[name] = f"'{name}' is not a field on this form"
        return result

    def capture(self, slug: str, answers: Answers, origin: CaptureOrigin) -> CaptureResult:
        form = self.find_active_form(origin.account_id, slug)
        result = self.validate(form, answers)
        if not result.complete:
            raise LeadsError("INCOMPLETE", _what_to_fix(result))
        _require_size(result.values)

        capture_id = capture_id_for(origin.account_id, form.form_id, origin.actor_id, result.values)
        existing = self._existing(origin.account_id, capture_id)
        if existing:
            return existing
        files = self.files.claim(
            form, result.values, conversation_id=origin.conversation_id, uploaded_by=origin.actor_id,
            capture_id=capture_id,
        )
        return self._save(
            origin, capture_id, answers=result.values, form_name=form.name, form_inputs=form.form_inputs,
            form=form, files=files,
        )

    def capture_ad_hoc(self, form_label: str, answers: list[LabelledAnswer], origin: CaptureOrigin) -> CaptureResult:
        """A lead with no lead form, from the deprecated `register_lead`: its answers carry their own labels."""
        form_inputs, values = ad_hoc_form(answers)
        _require_size(values)
        capture_id = capture_id_for(origin.account_id, f"ad-hoc:{form_label}", origin.actor_id, values)
        existing = self._existing(origin.account_id, capture_id)
        if existing:
            return existing
        return self._save(origin, capture_id, answers=values, form_name=form_label, form_inputs=form_inputs)

    def _existing(self, account_id: str, capture_id: str) -> CaptureResult | None:
        capture = self.repository.find_capture(account_id, capture_id)
        if capture is None:
            return None
        monthly_limit = self.limits.get_account_limits(account_id).lead_captures_per_month
        return CaptureResult(capture, duplicate=True, locked=capture.is_locked(monthly_limit))

    def _save(
        self,
        origin: CaptureOrigin,
        capture_id: str,
        *,
        answers: Answers,
        form_name: str,
        form_inputs: list[FormInput],
        form: LeadForm | None = None,
        files: list[CaptureFile] | None = None,
    ) -> CaptureResult:

        now = _now()
        source = origin.source
        capture = Capture(
            capture_id=capture_id,
            account_id=origin.account_id,
            form_id=form.form_id if form else None,
            form_slug=form.slug if form else None,
            form_name=form_name,
            form_version=form.version if form else None,
            form_inputs=form_inputs,
            answers=answers,
            files=files or [],
            agent_id=origin.agent_id,
            conversation_id=origin.conversation_id,
            actor_kind=origin.actor_kind,
            actor_id=origin.actor_id,
            actor_email=origin.actor_email,
            source=source,
            status=self.settings(origin.account_id).initial_status,
            # Test captures from the dashboard don't count towards the plan
            month_seq=None if source == "dashboard" else self.repository.count_towards_plan(
                origin.account_id, now.strftime("%Y-%m")
            ),
            created_at=now,
        )
        try:
            self.repository.save_capture(capture)
        except DuplicateCapture:
            # Saved by a call racing this one
            raced = self._existing(origin.account_id, capture_id)
            if raced is None:
                raise
            return raced
        monthly_limit = self.limits.get_account_limits(origin.account_id).lead_captures_per_month
        return CaptureResult(capture, duplicate=False, locked=capture.is_locked(monthly_limit))

    def list_captures(
        self, account_id: str, filters: CaptureFilters, *, limit: int, cursor: str | None = None
    ) -> CapturePage:
        monthly_limit = self.limits.get_account_limits(account_id).lead_captures_per_month
        items, next_cursor = self.repository.list_captures(
            account_id, filters, monthly_limit=monthly_limit, limit=limit, cursor=cursor
        )
        locked = 0
        if monthly_limit:
            locked = sum(max(0, count - monthly_limit) for count in self.repository.monthly_counts(account_id).values())
        return CapturePage(items=items, next_cursor=next_cursor, locked_count=locked)

    def get_capture(self, account_id: str, capture_id: str) -> Capture:
        capture = self.repository.find_capture(account_id, capture_id)
        if capture is None:
            raise capture_not_found()
        if capture.is_locked(self.limits.get_account_limits(account_id).lead_captures_per_month):
            raise LeadsError("LEAD_LOCKED", "This lead came in after your plan's monthly limit. Upgrade to see it.", 402)
        return capture

    def update_capture_status(self, account_id: str, capture_id: str, status: str) -> Capture:
        capture = self.get_capture(account_id, capture_id)
        if status not in self.settings(account_id).status_keys:
            raise LeadsError("UNKNOWN_STATUS", f"'{status}' is not one of this account's lead statuses.")
        return self.repository.update_capture_status(capture, status)

    def delete_capture(self, account_id: str, capture_id: str) -> None:
        """Allowed for locked leads too: privacy requests don't wait for an upgrade."""
        capture = self.repository.find_capture(account_id, capture_id)
        if capture is None:
            raise capture_not_found()
        self.repository.delete_capture(capture)
        self.files.delete_for(capture)

    def file_download_url(self, account_id: str, capture_id: str, file_id: str) -> str:
        """Locked like the capture itself: its files wait for the upgrade too."""
        return self.files.download_url(self.get_capture(account_id, capture_id), file_id)

    def usage(self, account_id: str) -> LeadUsage:
        limits = self.limits.get_account_limits(account_id)
        month = _now().strftime("%Y-%m")
        return LeadUsage(
            month=month,
            forms=sum(form.is_active for form in self.repository.list_forms(account_id)),
            forms_limit=limits.lead_forms,
            captures=self.repository.monthly_counts(account_id).get(month, 0),
            captures_limit=limits.lead_captures_per_month,
        )


def _require_size(answers: Answers) -> None:
    if len(json.dumps(answers)) > MAX_ANSWER_BYTES:
        raise LeadsError("TOO_LARGE", "These answers are too long to save. Shorten the longest ones.")


def _what_to_fix(result: SubmissionResult) -> str:
    """One sentence an agent can act on: what is still missing, and what to ask again."""
    parts = []
    if result.missing:
        parts.append(f"Still missing: {', '.join(result.missing)}.")
    if result.invalid:
        parts.append("Not valid: " + "; ".join(f"{name} ({reason})" for name, reason in result.invalid.items()) + ".")
    return " ".join(parts)


def _now() -> datetime:
    return datetime.now(timezone.utc)
