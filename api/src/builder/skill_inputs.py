"""Skill settings the person supplies, asked for by the system rather than by Ada.

Ada adds a skill as `- id: send_email` and plans. Before planning, the system reads each skill's manifest, finds
the required settings only the person knows (`SkillVariant.person_settings`) that the draft doesn't have, and shows a form in the chat for one skill at a time, built from the
manifest's own fields. The person's answers are checked with the manifest's validation and kept on the session;
every plan fills them into the draft. Once nothing is missing, the plan goes ahead as before.

Nothing here knows about any particular skill, so a new skill's settings are asked for with no change here.
Secrets are never asked for in the chat, since a form submission is a chat message; skills that need one are in
the `secrets` tier, which a blueprint can't build yet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

import yaml  # type: ignore[import-untyped,unused-ignore]

import src.form_models as form_models
from src.blueprints.skills_schema import AGENT_OPTION_SOURCES, SkillSetup, skill_variants
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

    #: "<agent resource>/<skill id>/<n>": the n-th entry of that skill on that agent. Survives Ada rewriting
    #: the draft, which entry indexes don't.
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

    @property
    def config_path(self) -> str:
        return f"resources.{self.resource}.skills[{self.index}].config"


def _load(text: Optional[str]) -> dict[str, Any]:
    try:
        data = yaml.safe_load(text or "")
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _skill_entries(data: dict[str, Any]):
    """(resource name, resource, entry index, entry, key) for every skill entry on every agent kept or built."""
    resources = data.get("resources")
    for name, resource in (resources.items() if isinstance(resources, dict) else []):
        if not isinstance(resource, dict) or resource.get("kind") != "Agent" or resource.get("remove"):
            continue
        entries = resource.get("skills")
        seen: dict[str, int] = {}
        for index, entry in enumerate(entries if isinstance(entries, list) else []):
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                continue
            occurrence = seen.get(entry["id"], 0)
            seen[entry["id"]] = occurrence + 1
            yield name, resource, index, entry, f"{name}/{entry['id']}/{occurrence}"


def _name(resource: dict[str, Any], fallback: str, params: Optional[dict[str, Any]]) -> str:
    """The name the person will see, with params filled in."""
    return str(substitute(str(resource.get("name") or fallback), params or {}))


def missing_inputs(text: Optional[str], params: Optional[dict[str, Any]] = None) -> list[SkillInput]:
    """Every skill entry missing a required setting its manifest says the person gives, in draft order."""
    variants = skill_variants()
    missing = []
    for name, resource, index, entry, key in _skill_entries(_load(text)):
        variant = variants.get(entry["id"])
        if variant is None or variant.setup == SkillSetup.SECRETS:
            continue
        config = entry.get("config") if isinstance(entry.get("config"), dict) else {}
        # Only what the person knows; settings Ada writes are hers, and a missing one is an issue for her to fix.
        fields = tuple(field for field in variant.person_settings if config.get(field.name) in (None, ""))
        if fields:
            missing.append(SkillInput(
                key=key,
                resource=name,
                index=index,
                skill_id=entry["id"],
                skill_name=variant.skill.manifest.name,
                skill_description=variant.skill.manifest.description.strip(),
                agent_name=_name(resource, name, params),
                fields=fields,
            ))
    return missing


class _LiteralDumper(yaml.SafeDumper):
    pass


def _represent_text(dumper: yaml.SafeDumper, value: str) -> yaml.Node:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_LiteralDumper.add_representer(str, _represent_text)


def fill_inputs(text: str, inputs: dict[str, dict[str, Any]]) -> str:
    """The draft with the person's answers in each skill's `config`. Settings the draft already has are kept."""
    if not inputs:
        return text
    data = _load(text)
    changed = False
    for _, _, _, entry, key in _skill_entries(data):
        given = inputs.get(key)
        if not given:
            continue
        config = entry.setdefault("config", {}) if isinstance(entry.get("config", {}), dict) else None
        for field_name, value in given.items():
            if config is not None and config.get(field_name) in (None, ""):
                config[field_name] = value
                changed = True
    if not changed:
        return text
    return yaml.dump(data, Dumper=_LiteralDumper, sort_keys=False, allow_unicode=True, width=120)


def covers(missing: list[SkillInput], path: str) -> bool:
    """Whether a validation issue is only about settings the person hasn't given yet."""
    return any(path == item.config_path or path.startswith(item.config_path + ".") for item in missing)


def _chat_input(
    field: form_models.FormInput, blueprint_agents: list[tuple[str, str]], context: FormOptionsContext
) -> dict[str, Any]:
    if field.options_source:
        field = hydrate_form_options(form_models.Form(form_name="", submit_path="", form_inputs=[field]), context).form_inputs[0]
    options = [{"value": option.value, "label": option.label} for option in field.options or []]
    if field.options_source and field.options_source.type in AGENT_OPTION_SOURCES:
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
    text: str,
    params: dict[str, Any],
    user_email: str,
    context: dict[str, Any],
    error: Optional[str] = None,
) -> dict[str, Any]:
    """A `ui_form_render` payload asking for `item`'s settings, from the manifest's own fields."""
    data = _load(text)
    resources = data.get("resources")
    resources = resources if isinstance(resources, dict) else {}
    blueprint_agents = [
        (name, _name(resource, name, params))
        for name, resource in resources.items()
        if isinstance(resource, dict) and resource.get("kind") == "Agent" and name != item.resource
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
    missing = missing_inputs(session.draft_yaml, session.draft_params)
    item = next((item for item in missing if item.key == pending.key), None)
    if item is None:
        session.pending_input = None
        return True
    answers = {field.name: values[field.name] for field in item.fields if values.get(field.name, "").strip()}
    entry = next(entry for _, _, _, entry, key in _skill_entries(_load(session.draft_yaml)) if key == item.key)
    try:
        get_skill_registry().validate_config(item.skill_id, {**(entry.get("config") or {}), **answers})
    except ValueError as e:
        session.pending_input = PendingInput(key=pending.key, label=pending.label, error=str(e))
        return True
    session.skill_inputs[item.key] = {**session.skill_inputs.get(item.key, {}), **answers}
    session.draft_yaml = fill_inputs(session.draft_yaml or "", session.skill_inputs)
    session.pending_input = None
    return True
