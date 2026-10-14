import pytest

from src.form_models import (
    FormInput,
    FormInputType,
    FormInputValidation,
    FormInputValidationFormat,
    SelectOption,
)
from src.form_validation import validate_form_value, validate_submission


def _text(name: str, **validation: object) -> FormInput:
    return FormInput(
        input_type=FormInputType.TEXT,
        name=name,
        label=name.title(),
        validation=FormInputValidation(**validation) if validation else None,
    )


@pytest.mark.parametrize(
    ("validation_format", "value", "stored"),
    [
        (FormInputValidationFormat.EMAIL, " Jane@Acme.com ", "jane@acme.com"),
        (FormInputValidationFormat.PHONE, "+44 (0)20 7946 0018", "+44 (0)20 7946 0018"),
        (FormInputValidationFormat.URL, "https://acme.com/about", "https://acme.com/about"),
        (FormInputValidationFormat.NUMBER, "42.5", "42.5"),
        (FormInputValidationFormat.DATE, "2026-10-15", "2026-10-15"),
    ],
)
def test_each_format_accepts_and_normalises_a_good_value(validation_format, value, stored):
    assert validate_form_value(_text("field", format=validation_format), value) == stored


@pytest.mark.parametrize(
    ("validation_format", "value"),
    [
        (FormInputValidationFormat.EMAIL, "jane@"),
        (FormInputValidationFormat.PHONE, "12345"),
        (FormInputValidationFormat.PHONE, "call me maybe"),
        (FormInputValidationFormat.URL, "javascript:alert(1)"),
        (FormInputValidationFormat.URL, "acme.com"),
        (FormInputValidationFormat.NUMBER, "forty"),
        (FormInputValidationFormat.DATE, "15/10/2026"),
    ],
)
def test_each_format_rejects_a_bad_value(validation_format, value):
    with pytest.raises(ValueError):
        validate_form_value(_text("field", format=validation_format), value)


def test_length_pattern_and_range_limits():
    assert validate_form_value(_text("code", min_length=2, max_length=4, pattern=r"[A-Z]+"), "ABC") == "ABC"
    for value in ("A", "ABCDE", "abc"):
        with pytest.raises(ValueError):
            validate_form_value(_text("code", min_length=2, max_length=4, pattern=r"[A-Z]+"), value)

    seats = _text("seats", format=FormInputValidationFormat.NUMBER, minimum=1, maximum=500)
    assert validate_form_value(seats, "20") == "20"
    with pytest.raises(ValueError, match="at most 500"):
        validate_form_value(seats, "501")


def test_select_stores_the_declared_option_casing():
    team_size = FormInput(
        input_type=FormInputType.SELECT,
        name="team_size",
        label="Team size",
        options=[SelectOption(value="Small", label="1-10"), SelectOption(value="Large", label="11+")],
    )
    assert validate_form_value(team_size, "small") == "Small"
    with pytest.raises(ValueError, match="Invalid value for team_size"):
        validate_form_value(team_size, "huge")


def test_checked_choices_accept_a_list_of_declared_values():
    interests = FormInput(
        input_type=FormInputType.CHOICE,
        name="interests",
        label="Interests",
        values=["Sales", "Support", "Billing"],
        attr={"variant": "checkbox"},
        validation=FormInputValidation(max_items=2),
    )
    assert validate_form_value(interests, ["sales", "Support", "Sales"]) == ["Sales", "Support"]
    with pytest.raises(ValueError):
        validate_form_value(interests, ["Sales", "Support", "Billing"])
    with pytest.raises(ValueError):
        validate_form_value(interests, ["Marketing"])


def test_file_uploads_are_ids_limited_by_max_items():
    evidence = FormInput(input_type=FormInputType.FILE_UPLOAD, name="evidence", label="Evidence")
    assert validate_form_value(evidence, "file_1") == ["file_1"]
    with pytest.raises(ValueError, match="at most 1 file"):
        validate_form_value(evidence, ["file_1", "file_2"])

    several = evidence.model_copy(update={"validation": FormInputValidation(max_items=3)})
    assert validate_form_value(several, ["file_1", "file_2"]) == ["file_1", "file_2"]


def test_submission_reports_every_problem_at_once():
    inputs = [
        _text("name"),
        _text("email", format=FormInputValidationFormat.EMAIL),
        _text("company"),
        FormInput(input_type=FormInputType.TEXT, name="notes", label="Notes", attr={"optional": "true"}),
    ]

    result = validate_submission(inputs, {"name": "Jane", "email": "not-an-email", "unknown": "ignored"})

    assert not result.complete
    assert result.missing == ["company"]
    assert set(result.invalid) == {"email"}
    assert result.values == {"name": "Jane"}


def test_complete_submission_returns_normalised_values():
    inputs = [_text("name"), _text("email", format=FormInputValidationFormat.EMAIL)]

    result = validate_submission(inputs, {"name": " Jane ", "email": "JANE@ACME.COM"})

    assert result.complete
    assert result.values == {"name": "Jane", "email": "jane@acme.com"}
