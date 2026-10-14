"""Server-side checks for values submitted through a schema-driven form.

Renderers treat `FormInput.validation` as hints; this module is what enforces it, for every form: skill
installs, lead forms and anything else built on `form_models`.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import urlparse

import src.form_models as form_models

EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")
PHONE_RE = re.compile(r"^\+?[0-9 ()\-.]+$")

_CHOICE_TYPES = {
    form_models.FormInputType.SELECT,
    form_models.FormInputType.SEARCH,
    form_models.FormInputType.CHOICE,
}


@dataclass(frozen=True)
class SubmissionResult:
    """Every problem with a submission at once, so a person (or an agent) can fix them together."""

    values: dict[str, Any] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    invalid: dict[str, str] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return not self.missing and not self.invalid


def validate_submission(inputs: list[form_models.FormInput], submitted: Mapping[str, Any]) -> SubmissionResult:
    """Check each declared input; names the form does not declare are ignored, so callers decide about them."""
    result = SubmissionResult()
    for input_def in inputs:
        value = submitted.get(input_def.name, input_def.value)
        if _is_blank(value):
            if not input_def.is_optional:
                result.missing.append(input_def.name)
            continue
        try:
            result.values[input_def.name] = validate_form_value(input_def, value)
        except ValueError as exc:
            result.invalid[input_def.name] = str(exc)
    return result


def validate_form_value(input_def: form_models.FormInput, value: Any) -> Any:
    """The value to store for `input_def`, normalised. Raises ValueError with a message naming the field."""
    if input_def.input_type == form_models.FormInputType.KEY_VALUE:
        return value
    if input_def.input_type == form_models.FormInputType.FILE_UPLOAD:
        return _validate_upload_ids(input_def, value)
    if isinstance(value, list):
        return _validate_checked_choices(input_def, value)

    text = str(value).strip()
    if input_def.input_type in _CHOICE_TYPES:
        return _validate_option(input_def, text)
    return _validate_text(input_def, text)


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


def _validate_text(input_def: form_models.FormInput, text: str) -> str:
    validation = input_def.validation
    if not validation:
        return text

    if validation.format == form_models.FormInputValidationFormat.EMAIL and validation.multiple:
        emails = parse_email_list(text, separator=validation.separator)
        _validate_item_count(input_def.name, emails, validation)
        return f"{validation.separator} ".join(emails)

    if validation.format:
        text = _FORMAT_CHECKS[validation.format](input_def, text)
    if validation.min_length is not None and len(text) < validation.min_length:
        raise ValueError(f"{input_def.label} must be at least {validation.min_length} characters")
    if validation.max_length is not None and len(text) > validation.max_length:
        raise ValueError(f"{input_def.label} must be at most {validation.max_length} characters")
    if validation.pattern and not re.fullmatch(validation.pattern, text):
        raise ValueError(f"{input_def.label} is not in the expected format")
    return text


def _check_email(input_def: form_models.FormInput, text: str) -> str:
    email = text.lower()
    if not EMAIL_RE.fullmatch(email):
        raise ValueError(f"Invalid email address for {input_def.name}")
    return email


def _check_phone(input_def: form_models.FormInput, text: str) -> str:
    digits = sum(character.isdigit() for character in text)
    if not PHONE_RE.fullmatch(text) or not 6 <= digits <= 20:
        raise ValueError(f"{input_def.label} must be a phone number")
    return text


def _check_url(input_def: form_models.FormInput, text: str) -> str:
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{input_def.label} must be a link starting with http:// or https://")
    return text


def _check_number(input_def: form_models.FormInput, text: str) -> str:
    try:
        number = float(text)
    except ValueError:
        raise ValueError(f"{input_def.label} must be a number") from None
    validation = input_def.validation
    if validation and validation.minimum is not None and number < validation.minimum:
        raise ValueError(f"{input_def.label} must be at least {validation.minimum:g}")
    if validation and validation.maximum is not None and number > validation.maximum:
        raise ValueError(f"{input_def.label} must be at most {validation.maximum:g}")
    return text


def _check_date(input_def: form_models.FormInput, text: str) -> str:
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise ValueError(f"{input_def.label} must be a date (YYYY-MM-DD)") from None


_FORMAT_CHECKS: dict[form_models.FormInputValidationFormat, Callable[[form_models.FormInput, str], str]] = {
    form_models.FormInputValidationFormat.EMAIL: _check_email,
    form_models.FormInputValidationFormat.PHONE: _check_phone,
    form_models.FormInputValidationFormat.URL: _check_url,
    form_models.FormInputValidationFormat.NUMBER: _check_number,
    form_models.FormInputValidationFormat.DATE: _check_date,
}


def _validate_option(input_def: form_models.FormInput, text: str) -> str:
    """The option as declared: matched case-insensitively, stored with the option's own casing."""
    allowed = _allowed_values(input_def)
    if not allowed:
        return text
    match = next((option for option in allowed if option.lower() == text.lower()), None)
    if match is None:
        raise ValueError(f"Invalid value for {input_def.name}. Allowed: {', '.join(sorted(allowed))}")
    return match


def _validate_checked_choices(input_def: form_models.FormInput, values: list[Any]) -> list[str]:
    if input_def.input_type != form_models.FormInputType.CHOICE:
        raise ValueError(f"{input_def.label} takes a single value")
    checked = list(dict.fromkeys(
        _validate_option(input_def, str(value).strip()) for value in values if str(value).strip()
    ))
    if input_def.validation:
        _validate_item_count(input_def.name, checked, input_def.validation)
    return checked


def _validate_upload_ids(input_def: form_models.FormInput, value: Any) -> list[str]:
    """Uploads are stored first and submitted by id; whoever owns the uploads checks the ids themselves."""
    ids = value if isinstance(value, list) else [value]
    upload_ids = [str(upload_id).strip() for upload_id in ids if str(upload_id).strip()]
    max_items = input_def.validation.max_items if input_def.validation and input_def.validation.max_items else 1
    if len(upload_ids) > max_items:
        raise ValueError(f"{input_def.label} allows at most {max_items} file(s)")
    return upload_ids


def _allowed_values(input_def: form_models.FormInput) -> list[str]:
    allowed = list(input_def.values or [])
    allowed.extend(option.value for option in input_def.options or [])
    return allowed


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


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, list):
        return not value
    # An empty key/value mapping is a deliberate "none", not a missing answer
    if isinstance(value, dict):
        return False
    return not str(value).strip()
