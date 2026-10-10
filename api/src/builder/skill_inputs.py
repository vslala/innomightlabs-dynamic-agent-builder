"""Skill settings the person supplies, asked for by the system rather than by Ila.

Ila adds a skill as `- id: send_email` and plans. Before planning, the system reads each skill's manifest, finds
the required settings only the person knows (`SkillVariant.person_settings`) that the draft doesn't have, and shows
a form in the chat for one skill at a time, built from the manifest's own fields. The person's answers are checked
with the manifest's validation and kept on the session; every plan fills them into the draft. Once nothing is
missing, the plan goes ahead as before.

Nothing here knows about any particular skill, so a new skill's settings are asked for with no change here.
Secrets are never asked for in the chat, since a form submission is a chat message; skills that need one are in
the `secrets` tier, which a blueprint can't build yet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

import src.form_models as form_models
from src.blueprints.draft import Draft
from src.blueprints.skills_schema import REFERENCE_OPTION_SOURCES, SkillSetup, skill_variants
from src.blueprints.validator import substitute
from src.builder.models import BuilderSession, PendingInput
from src.form_options import FormOptionsContext, hydrate_form_options
from src.skills.lead_capture.actions import render_custom_form
from src.skills.registry import get_skill_registry

#: The form input types a chat form can show; anything else is asked as free text.
CHAT_INPUT_TYPES = {
    form_models.FormInputType.TEXT: "text",
    form_models.FormInputType.TEXT_AREA: "text_area",
    form_models.FormInputType.SELECT: "select",
    form_models.FormInputType.SEARCH: "select",
    form_models.FormInputType.CHOICE: "choice",
}

_SUBMISSION = re.compile(r'^<form_submission label="([^"]+)">', re.MULTILINE)
_FIELD = re.compile(r'^- ([A-Za-z0-9_]+)="(.*)"$', re.MULTILINE)


@dataclass(frozen=True)
class SkillInput:
    """One skill entry in the draft that still needs settings from the person."""

    #: The entry's key in the draft (`SkillEntryRef.key`), which survives Ila rewriting it.
    key: str
    resource: str
    #: The entry's position in the agent's `skills`, for issue paths.
    index: int
    skill_id: str
    skill_name: str
    skill_description: str
    agent_name: str
    fields: tuple[form_models.FormInput, ...]

    @property
    def label(self) -> str:
        occurrence = int(self.key.rsplit("/", 1)[1])
        suffix = f" ({occurrence + 1})" if occurrence else ""
        return f"Set up {self.skill_name} for {self.agent_name}{suffix}"


def _name(resource: dict[str, Any], fallback: str, params: Optional[dict[str, Any]]) -> str:
    """The name the person will see, with params filled in."""
    return str(substitute(str(resource.get("name") or fallback), params or {}))


def missing_inputs(draft: Draft, params: Optional[dict[str, Any]] = None) -> list[SkillInput]:
    """Every skill entry missing a required setting its manifest says the person gives, in draft order."""
    variants = skill_variants()
    missing = []
    for ref in draft.skill_entries():
        variant = variants.get(ref.entry["id"])
        if variant is None or variant.setup == SkillSetup.SECRETS:
            continue
        config = ref.entry["config"] if isinstance(ref.entry.get("config"), dict) else {}
        # Only what the person knows; settings Ila writes are hers, and a missing one is an issue for her to fix.
        fields = tuple(field for field in variant.person_settings if config.get(field.name) in (None, ""))
        if fields:
            missing.append(SkillInput(
                key=ref.key,
                resource=ref.resource,
                index=ref.index,
                skill_id=ref.entry["id"],
                skill_name=variant.skill.manifest.name,
                skill_description=variant.skill.manifest.description.strip(),
                agent_name=_name(ref.agent, ref.resource, params),
                fields=fields,
            ))
    return missing


def _chat_input(
    field: form_models.FormInput, blueprint_agents: list[tuple[str, str]], context: FormOptionsContext
) -> dict[str, Any]:
    if field.options_source:
        field = hydrate_form_options(form_models.Form(form_name="", submit_path="", form_inputs=[field]), context).form_inputs[0]
    options = [{"value": option.value, "label": option.label} for option in field.options or []]
    if field.options_source and REFERENCE_OPTION_SOURCES.get(field.options_source.type) == "Agent":
        # Agents this blueprint is about to build can be chosen too; the blueprint names them.
        known = {option["value"] for option in options}
        options += [{"value": name, "label": f"{title} (in this build)"} for name, title in blueprint_agents if name not in known]
    attr = {key: value for key, value in (field.attr or {}).items() if key in ("placeholder", "help_text", "rows", "type")}
    chat: dict[str, Any] = {
        "input_type": CHAT_INPUT_TYPES.get(field.input_type, "text_area"),
        "name": field.name,
        "label": field.label,
    }
    if field.value is not None:
        chat["value"] = str(field.value)
    if options:
        chat["input_type"], chat["options"] = "select", options
    elif field.values:
        chat["values"] = list(field.values)
    if attr:
        chat["attr"] = attr
    return chat


def input_form(
    item: SkillInput,
    draft: Draft,
    params: dict[str, Any],
    user_email: str,
    context: dict[str, Any],
    error: Optional[str] = None,
) -> dict[str, Any]:
    """A `ui_form_render` payload asking for `item`'s settings, from the manifest's own fields."""
    blueprint_agents = [
        (name, _name(resource, name, params)) for name, resource in draft.kept("Agent") if name != item.resource
    ]
    options_context = FormOptionsContext(user_email=user_email)
    inputs = [_chat_input(field, blueprint_agents, options_context) for field in item.fields]
    if inputs:
        # Say what the skill is for, so the person knows why they're being asked.
        attr = inputs[0].setdefault("attr", {})
        purpose = f"{item.agent_name} will use {item.skill_name}: {item.skill_description}"
        attr["help_text"] = " ".join(part for part in (error, purpose, attr.get("help_text")) if part)
    return render_custom_form(
        arguments={"form_label": item.label, "submit_label": "Save", "form_inputs": inputs},
        config={},
        context=context,
    )


def submitted_values(message: str, label: str) -> Optional[dict[str, str]]:
    """The field values from the person's submission of the form called `label`, or None if it isn't one."""
    match = _SUBMISSION.search(message)
    if not match or match.group(1) != label:
        return None
    return {name: value for name, value in _FIELD.findall(message)}


def absorb_submission(session: BuilderSession, message: str) -> bool:
    """If `message` answers the form the session is waiting on, keep the answers and put them in the draft.

    Answers that fail the manifest's validation are not kept; the session keeps waiting, with the reason, so the
    next plan shows the form again with it. Returns whether the message was that form."""
    pending = session.pending_input
    if pending is None:
        return False
    values = submitted_values(message, pending.label)
    if values is None:
        return False
    draft = Draft(session.draft_yaml)
    item = next((item for item in missing_inputs(draft, session.draft_params) if item.key == pending.key), None)
    if item is None:
        session.pending_input = None
        return True
    answers = {field.name: values[field.name] for field in item.fields if values.get(field.name, "").strip()}
    entry = next(ref.entry for ref in draft.skill_entries() if ref.key == item.key)
    try:
        get_skill_registry().validate_config(item.skill_id, {**(entry.get("config") or {}), **answers})
    except ValueError as e:
        session.pending_input = PendingInput(key=pending.key, label=pending.label, error=str(e))
        return True
    session.skill_inputs[item.key] = {**session.skill_inputs.get(item.key, {}), **answers}
    session.draft_yaml = draft.with_skill_settings(session.skill_inputs).text
    session.pending_input = None
    return True
