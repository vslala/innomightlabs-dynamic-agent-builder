from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import src.form_models as form_models
from src.config import settings
from src.db import get_dynamodb_resource
from src.email import send_email

from .forms import parse_custom_inputs


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def register_lead(*, arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Persist lead submission for an agent and send an acknowledgement email."""
    form_label = _require_str(arguments.get("form_label"), "form_label")

    raw_answers = arguments.get("answers")
    if not isinstance(raw_answers, list):
        raise ValueError("'answers' must be an array")

    answers: list[dict[str, str]] = []
    for item in raw_answers:
        if not isinstance(item, dict):
            continue
        field_id = str(item.get("field_id") or "").strip()
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        if field_id and label and value:
            answers.append({"field_id": field_id, "label": label, "value": value})

    if not answers:
        raise ValueError("No valid answers provided")

    agent_id = str(context.get("agent_id") or "").strip()
    owner_email = str(context.get("owner_email") or "").strip()
    actor_email = str(context.get("actor_email") or "").strip()
    actor_id = str(context.get("actor_id") or "").strip()
    conversation_id = str(context.get("conversation_id") or "").strip()

    lead_id = uuid.uuid4().hex
    created_at = _iso_now()

    # Extract email + consent for acknowledgement.
    submitted_email = ""
    consent = ""
    for a in answers:
        fid = a["field_id"].lower()
        if fid in {"email", "work_email"} and not submitted_email:
            submitted_email = a["value"]
        if fid in {"contact_consent", "consent"} and not consent:
            consent = a["value"].strip().lower()

    if not submitted_email:
        raise ValueError("Missing email. Ask the user for a work email before registering the lead.")

    if consent not in {"yes", "true", "1", "on"}:
        raise ValueError(
            "Missing consent. Ask the user to confirm they agree to be contacted before registering the lead."
        )

    dynamodb = get_dynamodb_resource()
    table = dynamodb.Table(settings.dynamodb_table)

    item = {
        "pk": f"Agent#{agent_id}",
        "sk": f"Lead#{created_at}#{lead_id}",
        "entity_type": "LeadSubmission",
        "lead_id": lead_id,
        "agent_id": agent_id,
        "owner_email": owner_email,
        "conversation_id": conversation_id,
        "actor_email": actor_email,
        "actor_id": actor_id,
        "form_label": form_label,
        "answers": answers,
        "created_at": created_at,
    }

    table.put_item(Item=item)

    email_sent = False
    if submitted_email:
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
        "lead_id": lead_id,
        "form_label": form_label,
        "answer_count": len(answers),
        "email_sent": email_sent,
    }
