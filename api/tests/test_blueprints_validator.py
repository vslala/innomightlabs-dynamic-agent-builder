"""Blueprint parsing, validation and the generated schema. See docs/LLD-solution-blueprints.md."""

from typing import Any

import pytest

from src.blueprints.catalog import EXAMPLES_DIR, blueprint_json_schema, example_yaml, reference_markdown
from src.blueprints.issues import BlueprintInvalid, BlueprintIssue
from src.blueprints.validator import validate_blueprint
from src.config import settings

SITE_AGENT = example_yaml("site-agent") or ""
PARAMS = {"site_url": "https://acme.example/about", "business_name": "Acme"}


def issues_for(text: str, params: dict[str, Any] | None = None) -> list[BlueprintIssue]:
    with pytest.raises(BlueprintInvalid) as exc_info:
        validate_blueprint(text, params)
    return exc_info.value.issues


def issue_at(issues: list[BlueprintIssue], path: str) -> BlueprintIssue:
    matches = [issue for issue in issues if issue.path == path]
    assert matches, f"no issue at {path}: {issues}"
    return matches[0]


@pytest.mark.parametrize("path", sorted(EXAMPLES_DIR.glob("*.yaml")), ids=lambda p: p.stem)
def test_every_example_validates_against_the_real_skills(path):
    validated = validate_blueprint(path.read_text(encoding="utf-8"))
    assert validated.order


def test_site_agent_resolves_params_and_orders_resources():
    validated = validate_blueprint(SITE_AGENT, PARAMS)

    assert validated.order == ["site_kb", "assistant", "widget"]
    assert validated.params == {**PARAMS, "provider": "Bedrock"}
    agent = validated.blueprint.resources["assistant"]
    assert agent.name == "Acme assistant"
    assert "website assistant for Acme" in agent.instructions
    assert validated.blueprint.resources["widget"].allowed_origins == ["https://acme.example/about"]
    # Resource references in outputs are left for apply.
    assert validated.blueprint.outputs["snippet"].value == "{{ resources.widget.snippet }}"


def test_every_field_in_the_schema_is_described():
    schema = blueprint_json_schema()
    undescribed = [
        f"{definition}.{name}"
        for definition, body in [("Blueprint", schema), *schema["$defs"].items()]
        for name, prop in body.get("properties", {}).items()
        if not prop.get("description")
    ]
    assert undescribed == []


def test_reference_is_generated_from_the_schema():
    reference = reference_markdown()
    assert "## KnowledgeBase" in reference
    assert "### `lead_capture`" in reference
    assert "The most pages to read." in reference


def test_unknown_field_suggests_the_right_one_with_its_line():
    issues = issues_for(SITE_AGENT.replace("    skills:", "    skils:"))

    issue = issue_at(issues, "resources.assistant.skils")
    assert issue.hint == "Did you mean 'skills'?"
    assert issue.line is not None and "skils" in SITE_AGENT.replace("    skills:", "    skils:").splitlines()[issue.line - 1]


def test_unknown_kind_is_named_with_a_suggestion():
    issue = issue_at(issues_for(SITE_AGENT.replace("kind: WidgetKey", "kind: WidgetKy")), "resources.widget")
    assert "WidgetKy" in issue.message
    assert issue.hint == "Did you mean 'WidgetKey'?"


def test_several_problems_are_reported_together():
    broken = SITE_AGENT.replace("    skills:", "    skils:").replace("allow_guests: true", "allow_guest: true")
    paths = {issue.path for issue in issues_for(broken)}
    assert {"resources.assistant.skils", "resources.widget.allow_guest"} <= paths


def test_missing_and_wrong_kind_references():
    missing = issue_at(issues_for(SITE_AGENT.replace("agent: assistant", "agent: assistnt")), "resources.widget.agent")
    assert missing.hint == "Did you mean 'assistant'?"

    wrong_kind = issues_for(SITE_AGENT.replace("knowledge_bases: [site_kb]", "knowledge_bases: [widget]"))
    assert "is a WidgetKey" in issue_at(wrong_kind, "resources.assistant.knowledge_bases[0]").message


def test_undeclared_param_is_reported():
    issue = issue_at(
        issues_for(SITE_AGENT.replace("{{ params.business_name }} website", "{{ params.busines_name }} website")),
        "resources.site_kb.name",
    )
    assert issue.hint == "Did you mean 'business_name'?"


def test_required_param_and_url_param_are_checked():
    missing = issues_for(SITE_AGENT, {"site_url": "https://acme.example"})
    assert issue_at(missing, "params.business_name").message == "'Business name' is required."

    bad_url = issues_for(SITE_AGENT, {**PARAMS, "site_url": "acme.example"})
    assert "web address" in issue_at(bad_url, "params.site_url").message

    unknown = issues_for(SITE_AGENT, {**PARAMS, "sites_url": "x"})
    assert issue_at(unknown, "params.sites_url").hint == "Did you mean 'site_url'?"


def test_resource_templates_are_only_allowed_in_outputs():
    issues = issues_for(SITE_AGENT.replace('name: "{{ params.business_name }} assistant"', 'name: "{{ resources.site_kb.id }}"'))
    assert "only be used in `outputs`" in issue_at(issues, "resources.assistant.name").message


def test_outputs_can_only_use_attributes_a_kind_exposes():
    issues = issues_for(SITE_AGENT.replace("{{ resources.widget.snippet }}", "{{ resources.widget.snipet }}"))
    issue = issue_at(issues, "outputs.snippet.value")
    assert issue.hint == "Did you mean 'snippet'?"


def test_invalid_resource_name_is_explained():
    issues = issues_for(SITE_AGENT.replace("  widget:\n    kind: WidgetKey", "  Widget Key:\n    kind: WidgetKey"))
    assert any("isn't a valid name" in issue.message for issue in issues)


def test_widget_origins_must_be_web_addresses():
    issues = issues_for(SITE_AGENT.replace('allowed_origins: ["{{ params.site_url }}"]', 'allowed_origins: ["acme"]'))
    assert "isn't a web address" in issue_at(issues, "resources.widget.allowed_origins[0]").message


def test_yaml_anchors_are_rejected():
    issues = issues_for(SITE_AGENT.replace("  site_kb:\n", "  site_kb: &kb\n"))
    assert "anchors" in issues[0].message


def test_oversized_and_malformed_yaml(monkeypatch):
    monkeypatch.setattr(settings, "blueprint_max_bytes", 100)
    assert "larger than" in issues_for(SITE_AGENT)[0].message
    monkeypatch.setattr(settings, "blueprint_max_bytes", 64 * 1024)

    malformed = issues_for("apiVersion: innomight/v1\nkind: [Blueprint\n")
    assert "isn't valid YAML" in malformed[0].message
    assert malformed[0].line is not None


def test_missing_top_level_fields_fall_back_to_the_document_line():
    # A top-level path has no parent to fall back to; this used to loop forever.
    issues = issues_for("kind: Blueprint\n")
    assert issue_at(issues, "apiVersion").message == "'apiVersion' is required."


def test_too_many_resources(monkeypatch):
    monkeypatch.setattr(settings, "blueprint_max_resources", 2)
    assert "at most 2 resources" in issue_at(issues_for(SITE_AGENT), "resources").message
