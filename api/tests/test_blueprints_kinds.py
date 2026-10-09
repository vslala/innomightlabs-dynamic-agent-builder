"""The kinds are the one list of what a blueprint can use, and each kind says how it's shown."""

from typing import get_args

import pytest

from src.blueprints.catalog import example_yaml
from src.blueprints.document import Blueprint, Resource
from src.blueprints.kinds import KIND_NAMES, RESOURCE_KINDS, LookupKind, ManagedKind, kind_for, managed_kind_for
from src.blueprints.validator import validate_blueprint


def test_a_blueprint_accepts_exactly_the_kinds_in_the_registry():
    union, _ = get_args(Resource)
    assert {spec.model_fields["kind"].annotation.__args__[0] for spec in get_args(union)} == set(KIND_NAMES)
    assert Blueprint.model_fields["resources"].annotation is not None


def test_every_kind_is_either_managed_or_looked_up():
    for kind in RESOURCE_KINDS:
        assert isinstance(kind, (ManagedKind, LookupKind)), kind.kind
        assert not (isinstance(kind, ManagedKind) and isinstance(kind, LookupKind)), kind.kind


def test_a_looked_up_kind_is_never_created_or_deleted():
    assert managed_kind_for("Agent").kind == "Agent"
    with pytest.raises(TypeError, match="never creates"):
        managed_kind_for("McpConnection")


def test_each_kind_names_and_draws_its_resources():
    resources = validate_blueprint(example_yaml("web-research-team") or "", {}).blueprint.resources
    titles = {name: kind_for(spec.kind).title(name, spec, resources) for name, spec in resources.items()}
    assert titles["web_search"] == "Tavily"
    for name, spec in resources.items():
        assert kind_for(spec.kind).card_details(spec), name


def test_an_unnamed_widget_key_is_named_after_its_agent():
    resources = validate_blueprint(
        example_yaml("site-agent") or "", {"site_url": "https://acme.example", "business_name": "Acme"}
    ).blueprint.resources
    widget = resources["widget"]
    assert kind_for("WidgetKey").title("widget", widget.model_copy(update={"name": None}), resources).endswith(" widget")


def test_dashboard_links_come_from_the_kinds():
    assert kind_for("Agent").dashboard_path.format(id="a-1") == "/dashboard/agents/a-1"
    assert kind_for("WidgetKey").dashboard_path == ""
