from __future__ import annotations

from typing import Any

import src.form_models as form_models


SAFE_INPUT_TYPES = {
    form_models.FormInputType.TEXT,
    form_models.FormInputType.TEXT_AREA,
    form_models.FormInputType.SELECT,
    form_models.FormInputType.CHOICE,
}

INPUT_TYPE_ALIASES: dict[str, tuple[form_models.FormInputType, dict[str, str]]] = {
    "text": (form_models.FormInputType.TEXT, {}),
    "text_area": (form_models.FormInputType.TEXT_AREA, {}),
    "textarea": (form_models.FormInputType.TEXT_AREA, {}),
    "select": (form_models.FormInputType.SELECT, {}),
    "dropdown": (form_models.FormInputType.SELECT, {}),
    "choice": (form_models.FormInputType.CHOICE, {}),
    "radio": (form_models.FormInputType.CHOICE, {"variant": "radio"}),
    "checkbox": (form_models.FormInputType.CHOICE, {"variant": "checkbox"}),
    "email": (form_models.FormInputType.TEXT, {"type": "email"}),
    "phone": (form_models.FormInputType.TEXT, {"type": "tel"}),
    "tel": (form_models.FormInputType.TEXT, {"type": "tel"}),
    "url": (form_models.FormInputType.TEXT, {"type": "url"}),
}


def _normalize_input_type(raw: Any) -> tuple[form_models.FormInputType, dict[str, str]]:
    normalized = str(raw or "").strip().lower()
    if not normalized:
        raise ValueError("Missing input_type")

    alias = INPUT_TYPE_ALIASES.get(normalized)
    if alias:
        return alias

    try:
        return form_models.FormInputType(normalized), {}
    except Exception as exc:
        raise ValueError(f"Unsupported input_type '{normalized}'") from exc


def parse_custom_inputs(raw: Any, *, max_fields: int = 12) -> list[form_models.FormInput]:
    """Parse and validate custom form inputs.

    Guardrails:
    - limit number of fields
    - only allow safe input types
    - enforce basic string limits

    Backward compatible with FormInput shape.
    """
    if not isinstance(raw, list):
        raise ValueError("'form_inputs' must be an array")

    if len(raw) > max_fields:
        raise ValueError(f"Too many fields (max {max_fields})")

    parsed: list[form_models.FormInput] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"form_inputs[{i}] must be an object")

        # minimal required
        input_type_raw = item.get("input_type")
        name = str(item.get("name") or "").strip()
        label = str(item.get("label") or "").strip()
        if not name or not label or not input_type_raw:
            raise ValueError(f"form_inputs[{i}] must include input_type, name, label")

        try:
            input_type, attr_defaults = _normalize_input_type(input_type_raw)
        except ValueError as exc:
            raise ValueError(f"Invalid input_type for form_inputs[{i}]: {exc}") from exc

        if input_type not in SAFE_INPUT_TYPES:
            raise ValueError(f"Unsupported input_type for lead capture: {input_type.value}")

        value = item.get("value")
        values = item.get("values")
        options = item.get("options")
        attr = item.get("attr")

        # Basic bounds
        if len(name) > 64:
            raise ValueError(f"form_inputs[{i}].name too long")
        if len(label) > 120:
            raise ValueError(f"form_inputs[{i}].label too long")

        if attr is not None and not isinstance(attr, dict):
            raise ValueError(f"form_inputs[{i}].attr must be an object")

        normalized_attr = {k: str(v) for k, v in attr_defaults.items()}
        if attr:
            normalized_attr.update({str(k): str(v) for k, v in attr.items()})

        # Pydantic will validate the remainder.
        parsed.append(
            form_models.FormInput(
                input_type=input_type,
                name=name,
                label=label,
                value=value if value is None else str(value),
                values=values,
                options=options,
                attr=normalized_attr or None,
            )
        )

    return parsed
