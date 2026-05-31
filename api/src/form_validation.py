from __future__ import annotations

import re
from typing import Any

import src.form_models as form_models

EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")


def parse_email_list(value: str, *, separator: str = ",") -> list[str]:
    emails: list[str] = []
    seen: set[str] = set()
    for part in value.split(separator):
        email = part.strip().lower()
        if not email:
            continue
        if not EMAIL_RE.fullmatch(email):
            raise ValueError(f"Invalid email address: {email}")
        if email not in seen:
            emails.append(email)
            seen.add(email)
    return emails


def validate_form_value(field: form_models.FormInput, value: Any) -> str:
    normalized = str(value).strip()
    validation = field.validation
    if not validation:
        return normalized

    if validation.format == form_models.FormInputValidationFormat.EMAIL:
        if validation.multiple:
            emails = parse_email_list(normalized, separator=validation.separator)
            _validate_item_count(field.name, emails, validation)
            return f"{validation.separator} ".join(emails)

        if not EMAIL_RE.fullmatch(normalized.lower()):
            raise ValueError(f"Invalid email address for {field.name}")
        _validate_item_count(field.name, [normalized], validation)
        return normalized.lower()

    return normalized


def _validate_item_count(
    field_name: str,
    values: list[str],
    validation: form_models.FormInputValidation,
) -> None:
    if validation.min_items is not None and len(values) < validation.min_items:
        raise ValueError(
            f"Field {field_name} requires at least {validation.min_items} item(s)"
        )
    if validation.max_items is not None and len(values) > validation.max_items:
        raise ValueError(
            f"Field {field_name} allows at most {validation.max_items} item(s)"
        )
