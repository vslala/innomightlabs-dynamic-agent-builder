"""Each param type reads its value and asks for it in the run form; the spec, validator and form share them."""

from typing import get_args

import pytest

import src.form_models as form_models
from src.blueprints.catalog import params_form
from src.blueprints.document import Blueprint
from src.blueprints.params import PARAM_TYPES, param_type
from src.blueprints.spec import ParamSpec


@pytest.mark.parametrize(
    "type_, value, expected, error",
    [
        ("string", "  hi ", "hi", None),
        ("text", "  two\nlines ", "  two\nlines ", None),
        ("url", "https://acme.example", "https://acme.example", None),
        ("url", "acme.example", None, "web address"),
        ("integer", " 12 ", 12, None),
        ("integer", "twelve", None, "whole number"),
        ("boolean", "Yes", True, None),
        ("boolean", False, False, None),
        ("boolean", "maybe", None, "true or false"),
        ("choice", "b", "b", None),
        ("choice", "c", None, "one of: a, b"),
    ],
)
def test_each_type_reads_its_value(type_, value, expected, error):
    spec = ParamSpec(type=type_, label="X", options=["a", "b"] if type_ == "choice" else [])
    got, problem = param_type(spec).coerce(spec, value)
    assert got == expected
    assert (problem is None) if error is None else (error in problem)


def test_the_spec_offers_exactly_the_registered_types():
    assert set(get_args(ParamSpec.model_fields["type"].annotation)) == set(PARAM_TYPES)


def test_the_run_form_asks_for_each_type_its_own_way():
    blueprint = Blueprint.model_validate({
        "apiVersion": "innomight/v1",
        "kind": "Blueprint",
        "metadata": {"name": "x", "title": "X"},
        "params": {
            "site": {"type": "url", "label": "Site"},
            "notes": {"type": "text", "label": "Notes"},
            "public": {"type": "boolean", "label": "Public", "default": True},
            "tone": {"type": "choice", "label": "Tone", "options": ["warm", "plain"]},
        },
        "resources": {"kb": {"kind": "KnowledgeBase", "name": "Docs"}},
    })
    form = {field.name: field for field in params_form(blueprint).form_inputs}
    assert form["site"].attr == {"placeholder": "https://example.com"}
    assert form["notes"].input_type is form_models.FormInputType.TEXT_AREA
    assert (form["public"].values, form["public"].value) == (["true", "false"], "true")
    assert form["tone"].values == ["warm", "plain"]
