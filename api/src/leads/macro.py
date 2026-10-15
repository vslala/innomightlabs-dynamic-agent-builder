"""`{{ lead_form:<slug> }}`: a lead form, written out for the agent that is to fill it in."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.form_models import FormInput, FormInputType
from src.leads.models import LeadForm
from src.leads.repository import LeadsRepository

if TYPE_CHECKING:
    from src.agents.instructions import MacroContext

log = logging.getLogger(__name__)

LEAD_CAPTURE_SKILL = "lead_capture"


def render_lead_form(slug: str, context: MacroContext) -> str:
    form = LeadsRepository().find_form_by_slug(context.account_id, slug)
    if form is None:
        log.warning("Instructions name a lead form that doesn't exist: %s in account %s", slug, context.account_id)
        return f'[lead form "{slug}" not found]'
    if not form.is_active:
        return f'[lead form "{slug}" is not collecting]'

    block = describe_for_agent(form)
    if LEAD_CAPTURE_SKILL not in context.skill_ids:
        return block + "\nLead Capture is not enabled for you here, so you cannot save these details. Don't say you have."
    return block


def describe_for_agent(form: LeadForm) -> str:
    lines = [f'<lead_form slug="{form.slug}" version="{form.version}">']
    if form.purpose:
        lines.append(f"Purpose: {form.purpose}")
    lines.append("Fields:")
    lines.extend(f"- {_describe_input(form_input)}" for form_input in form.form_inputs)
    lines.extend([
        "How to capture:",
        "- Gather these over the conversation; you don't need to ask for them all at once.",
        "- Remember what you learn about this person in memory, so you can carry on at a later visit.",
        f'- Use the lead_capture skill: validate_lead with form "{form.slug}" shows what is still missing,'
        " and render_lead_form shows the person a form when that is easier.",
        f'- When every required field is known, call capture_lead with form "{form.slug}" and the answers by field name.',
        "- Only tell the person their details are saved after capture_lead succeeds.",
        "</lead_form>",
    ])
    return "\n".join(lines)


def _describe_input(form_input: FormInput) -> str:
    """`email (email, required): Work email. Ask only after you have helped them.`"""
    need = "optional" if form_input.is_optional else "required"
    description = f"{form_input.name} ({_kind(form_input)}, {need}): {form_input.label}"
    hint = (form_input.attr or {}).get("agent_hint")
    return f"{description}. {hint}" if hint else description


def _kind(form_input: FormInput) -> str:
    options = [option.value for option in form_input.options or []] + list(form_input.values or [])
    variant = (form_input.attr or {}).get("variant")
    if form_input.input_type == FormInputType.FILE_UPLOAD:
        return "file upload; files can't be typed in chat, so ask with render_lead_form"
    if form_input.input_type == FormInputType.SELECT:
        return "one of: " + " | ".join(options)
    if form_input.input_type == FormInputType.CHOICE:
        if len(options) == 1:
            return f'checkbox, "{options[0]}" when ticked'
        return ("any of: " if variant == "checkbox" else "one of: ") + " | ".join(options)
    if form_input.validation and form_input.validation.format:
        return form_input.validation.format.value
    return "long text" if form_input.input_type == FormInputType.TEXT_AREA else "text"
