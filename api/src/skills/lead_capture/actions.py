from __future__ import annotations

from typing import Any

import src.form_models as form_models
from src.email import send_email
from src.leads.errors import LeadsError
from src.leads.models import LabelledAnswer
from src.leads.service import CaptureOrigin, LeadsService
from src.skills.models import ActorKind
from src.skills.runtime_context import account_of

from .forms import parse_custom_inputs


def _require_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing or invalid '{name}'")
    return value.strip()


def _submit_path(context: dict[str, Any]) -> str:
    agent_id = str(context.get("agent_id") or "").strip()
    conversation_id = str(context.get("conversation_id") or "").strip()
    return f"/agents/{agent_id}/{conversation_id}/lead-capture/submit"


def _ui_form_payload(form: form_models.Form, *, submit_label: str) -> dict[str, Any]:
    return {
        "type": "ui_form_render",
        "form": form.model_dump(mode="json"),
        "submit_label": submit_label,
    }


def render_form(*, arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Return a widget-renderable default lead capture form."""
    form_label = _require_str(arguments.get("form_label"), "form_label")
    submit_label = str(arguments.get("submit_label") or "Submit").strip() or "Submit"

    inputs: list[form_models.FormInput] = [
        form_models.FormInput(
            input_type=form_models.FormInputType.TEXT,
            name="name",
            label="Name",
            attr={"placeholder": "Your name"},
        ),
        form_models.FormInput(
            input_type=form_models.FormInputType.TEXT,
            name="email",
            label="Work email",
            attr={"placeholder": "name@company.com"},
        ),
        form_models.FormInput(
            input_type=form_models.FormInputType.TEXT,
            name="company",
            label="Company",
            attr={"placeholder": "Company name"},
        ),
        form_models.FormInput(
            input_type=form_models.FormInputType.TEXT_AREA,
            name="request",
            label="What would you like help with?",
            attr={"placeholder": "Tell us what you're trying to do"},
        ),
        form_models.FormInput(
            input_type=form_models.FormInputType.CHOICE,
            name="contact_consent",
            label="I agree to be contacted about my request",
            values=["yes"],
        ),
    ]

    form = form_models.Form(
        form_name=form_label,
        submit_path=_submit_path(context),
        form_inputs=inputs,
    )

    return _ui_form_payload(form, submit_label=submit_label)


def render_custom_form(*, arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Render a bounded custom form schema in the widget.

    The caller (LLM) provides form_inputs. We validate and normalize them so the
    UI receives a safe, predictable schema.
    """
    form_label = _require_str(arguments.get("form_label"), "form_label")
    submit_label = str(arguments.get("submit_label") or "Submit").strip() or "Submit"

    inputs = parse_custom_inputs(arguments.get("form_inputs"))

    form = form_models.Form(
        form_name=form_label,
        submit_path=_submit_path(context),
        form_inputs=inputs,
    )

    return _ui_form_payload(form, submit_label=submit_label)


def validate_lead(*, arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """What a lead form still needs, without saving anything."""
    leads = LeadsService()
    try:
        form = leads.find_active_form(account_of(context), _require_str(arguments.get("form"), "form"))
    except LeadsError as refused:
        return _refusal(refused)
    result = leads.validate(form, _answers(arguments))
    return {"complete": result.complete, "missing": result.missing, "invalid": result.invalid}


def render_lead_form(*, arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """The account's own form, so the person sees the owner's fields rather than ones the model made up."""
    try:
        form = LeadsService().find_active_form(account_of(context), _require_str(arguments.get("form"), "form"))
    except LeadsError as refused:
        return _refusal(refused)
    known = _answers(arguments, key="prefill")
    only_missing = arguments.get("only_missing", True) is not False
    inputs = [
        form_input.model_copy(update={"value": str(known[form_input.name])}) if form_input.name in known else form_input
        for form_input in form.form_inputs
        if not (only_missing and form_input.name in known)
    ]
    payload = _ui_form_payload(
        form.as_form(_submit_path(context)).model_copy(update={"form_inputs": inputs}),
        submit_label=str(arguments.get("submit_label") or "Submit").strip() or "Submit",
    )
    # The widget sends uploads against the stored form, so it needs to know which one this is
    payload["lead_form"] = form.slug
    return payload


def capture_lead(*, arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Save a completed lead form. Anything missing or invalid comes back as a message to act on."""
    try:
        result = LeadsService().capture(_require_str(arguments.get("form"), "form"), _answers(arguments), _origin(context))
    except LeadsError as refused:
        return _refusal(refused)
    return {"ok": True, "capture_id": result.capture.capture_id, "duplicate": result.duplicate}


def register_lead(*, arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Deprecated: save a lead without a lead form, and send the acknowledgement email it always has."""
    form_label = _require_str(arguments.get("form_label"), "form_label")

    raw_answers = arguments.get("answers")
    if not isinstance(raw_answers, list):
        raise ValueError("'answers' must be an array")
    answers = [
        LabelledAnswer(
            field_id=str(item.get("field_id") or "").strip(),
            label=str(item.get("label") or "").strip(),
            value=str(item.get("value") or "").strip(),
        )
        for item in raw_answers
        if isinstance(item, dict)
    ]
    answers = [answer for answer in answers if answer.field_id and answer.label and answer.value]
    if not answers:
        raise ValueError("No valid answers provided")

    by_field = {answer.field_id.lower(): answer.value for answer in answers}
    submitted_email = by_field.get("email") or by_field.get("work_email") or ""
    consent = (by_field.get("contact_consent") or by_field.get("consent") or "").lower()
    if not submitted_email:
        raise ValueError("Missing email. Ask the user for a work email before registering the lead.")
    if consent not in {"yes", "true", "1", "on"}:
        raise ValueError(
            "Missing consent. Ask the user to confirm they agree to be contacted before registering the lead."
        )

    result = LeadsService().capture_ad_hoc(form_label, answers, _origin(context))

    email_sent = False
    if not result.duplicate:
        subject = f"We received your request: {form_label}"
        body = (
            "Thanks — we’ve received your request and someone will get back to you soon.\n\n"
            f"Request type: {form_label}\n"
            "\n"
            "If you didn’t submit this request, you can ignore this email."
        )
        email_sent = send_email(submitted_email, subject, body)

    return {
        "ok": True,
        "lead_id": result.capture.capture_id,
        "form_label": form_label,
        "answer_count": len(answers),
        "email_sent": email_sent,
    }


def _origin(context: dict[str, Any]) -> CaptureOrigin:
    """Who and where from the run itself; a lead never names its own account."""
    return CaptureOrigin(
        account_id=account_of(context),
        agent_id=str(context.get("agent_id") or ""),
        conversation_id=str(context.get("conversation_id") or "") or None,
        actor_kind=ActorKind(context.get("actor_kind") or ActorKind.OWNER.value),
        actor_id=str(context.get("actor_id") or context.get("actor_email") or ""),
        actor_email=str(context.get("actor_email") or "") or None,
    )


def _answers(arguments: dict[str, Any], key: str = "answers") -> dict[str, Any]:
    answers = arguments.get(key) or {}
    if not isinstance(answers, dict):
        raise ValueError(f"'{key}' must be an object of field name to value")
    return answers


def _refusal(refused: LeadsError) -> dict[str, Any]:
    return {"ok": False, "code": refused.code, "message": refused.message}
