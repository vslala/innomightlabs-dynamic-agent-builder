"""
Validates and loads skill form schemas.

Ensures schema.json files conform to the Form model format
used by the frontend form components.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.form_models import Form, FormInput, FormInputType, SelectOption

log = logging.getLogger(__name__)

VALID_INPUT_TYPES = {t.value for t in FormInputType}


def parse_form_schema(raw: dict[str, Any]) -> Optional[Form]:
    """
    Parse and validate a raw schema dictionary into a Form model.

    Args:
        raw: The raw schema as loaded from schema.json.

    Returns:
        A validated Form instance, or None if invalid.
    """
    if not isinstance(raw, dict):
        return None

    form_name = raw.get("form_name")
    submit_path = raw.get("submit_path")
    form_inputs_raw = raw.get("form_inputs")

    if not form_name or not isinstance(form_name, str):
        log.warning("Schema missing or invalid form_name")
        return None

    if not submit_path or not isinstance(submit_path, str):
        log.warning("Schema missing or invalid submit_path")
        return None

    if not isinstance(form_inputs_raw, list):
        form_inputs_raw = []

    form_inputs: list[FormInput] = []
    for i, inp in enumerate(form_inputs_raw):
        if not isinstance(inp, dict):
            continue
        parsed = _parse_form_input(inp)
        if parsed is not None:
            form_inputs.append(parsed)
        else:
            log.warning("Skipping invalid form input at index %d", i)

    return Form(
        form_name=form_name,
        submit_path=submit_path,
        form_inputs=form_inputs,
    )


def _parse_form_input(raw: dict[str, Any]) -> Optional[FormInput]:
    """Parse a single form input from raw dict."""
    input_type_str = raw.get("input_type")
    name = raw.get("name")
    label = raw.get("label")

    if not input_type_str or not isinstance(input_type_str, str):
        return None
    if input_type_str not in VALID_INPUT_TYPES:
        log.warning("Unknown input_type: %s", input_type_str)
        return None
    if not name or not isinstance(name, str):
        return None
    if not label or not isinstance(label, str):
        return None

    input_type = FormInputType(input_type_str)

    value = raw.get("value") if isinstance(raw.get("value"), str) else None
    values = raw.get("values") if isinstance(raw.get("values"), list) else None
    options = _parse_options(raw.get("options"))
    attr = raw.get("attr") if isinstance(raw.get("attr"), dict) else None

    return FormInput(
        input_type=input_type,
        name=name,
        label=label,
        value=value,
        values=values,
        options=options,
        attr=attr,
    )


def _parse_options(raw: Any) -> Optional[list[SelectOption]]:
    """Parse select options from raw list."""
    if not isinstance(raw, list):
        return None
    options: list[SelectOption] = []
    for item in raw:
        if isinstance(item, dict) and "value" in item and "label" in item:
            options.append(SelectOption(value=str(item["value"]), label=str(item["label"])))
    return options if options else None
