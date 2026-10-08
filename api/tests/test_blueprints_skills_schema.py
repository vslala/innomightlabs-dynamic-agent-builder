"""Blueprint skill entries are generated from the skill manifests, never written by hand."""

from pathlib import Path
from textwrap import dedent

import pytest

from src.blueprints.catalog import blueprint_json_schema
from src.blueprints.issues import BlueprintInvalid
from src.blueprints.skills_schema import skill_variants
from src.blueprints.validator import validate_blueprint
from src.skills.registry import SkillRegistry, get_skill_registry

#: Install-form fields that had no `attr.help_text` when blueprints shipped. Shrink it as manifests
#: are touched; a new field without help text fails this test.
FIELDS_WITHOUT_HELP_TEXT = {
    "agent2agent_client.default_credentials", "agent2agent_client.registry_set_name",
    "agent_invocation.target_agent_id", "agent_invocation.usage_description",
    "aws_cli.aws_access_key_id", "aws_cli.aws_region", "aws_cli.aws_secret_access_key",
    "aws_cli.command_policy_yaml", "google_ads.access", "google_ads.allow_advanced_mutate",
    "league_insights_report.default_routing_region", "league_insights_report.report_agent_id",
    "league_insights_report.riot_api_key", "riot_lol_api_client.default_platform_region",
    "riot_lol_api_client.default_routing_region", "riot_lol_api_client.riot_api_key", "send_email.to",
    "wordpress_search.app_password", "wordpress_search.cf_bypass_token", "wordpress_search.site_url",
    "wordpress_search.username",
}

NOTES_MANIFEST = """
id: notes
namespace: test.notes
name: Notes
description: Keep notes.
form:
  - input_type: text
    name: title
    label: Title
    attr:
      help_text: What the notes are about.
  - input_type: select
    name: tone
    label: Tone
    values: [formal, casual]
    value: casual
  - input_type: key_value
    name: labels
    label: Labels
    attr:
      optional: "true"
  - input_type: password
    name: token
    label: API token
    attr:
      optional: "true"
"""

OWNER_MANIFEST = """
id: my_accounts
namespace: test.owner
name: My Accounts
description: Uses the owner's accounts.
owner_only: true
"""

LOCKED_MANIFEST = """
id: locked
namespace: test.locked
name: Locked
description: Needs a secret to install.
form:
  - input_type: password
    name: api_key
    label: API key
"""

BLUEPRINT = """
apiVersion: innomight/v1
kind: Blueprint
metadata: {name: notes-agent, title: Notes agent}
resources:
  helper:
    kind: Agent
    name: Helper
    provider: Bedrock
    instructions: Help.
    skills:
SKILLS
"""


def write_skill(root: Path, folder: str, manifest: str) -> None:
    (root / folder).mkdir()
    (root / folder / "manifest.yml").write_text(dedent(manifest), encoding="utf-8")


@pytest.fixture
def registry(tmp_path: Path) -> SkillRegistry:
    write_skill(tmp_path, "notes", NOTES_MANIFEST)
    write_skill(tmp_path, "my_accounts", OWNER_MANIFEST)
    return SkillRegistry(root_dir=tmp_path)


def blueprint_with(skills: str) -> str:
    return BLUEPRINT.replace("SKILLS", dedent(skills).strip("\n").replace("\n", "\n      ").join(["      ", ""]))


def issues(registry: SkillRegistry, skills: str):
    with pytest.raises(BlueprintInvalid) as exc_info:
        validate_blueprint(blueprint_with(skills), registry=registry)
    return exc_info.value.issues


def test_every_registered_skill_gets_a_variant():
    registry = get_skill_registry()
    assert set(skill_variants(registry)) == {loaded.manifest.id for loaded in registry.list()}


def test_a_new_manifest_reaches_the_schema_after_reload(registry: SkillRegistry, tmp_path: Path):
    before = registry.version
    assert "locked" not in skill_variants(registry)

    write_skill(tmp_path, "locked", LOCKED_MANIFEST)
    registry.reload()

    assert registry.version != before
    assert "locked" in skill_variants(registry)
    assert "Skill_locked" in blueprint_json_schema(registry)["$defs"]


def test_form_fields_become_config_fields(registry: SkillRegistry):
    defs = blueprint_json_schema(registry)["$defs"]
    config = defs["notes_config"]

    assert config["properties"]["title"]["description"] == "What the notes are about."
    assert config["properties"]["tone"]["description"] == "Tone"
    assert config["properties"]["tone"]["default"] == "casual"
    assert config["properties"]["labels"]["anyOf"][0]["type"] == "object"
    assert config["required"] == ["title"]
    assert config["additionalProperties"] is False


def test_secrets_are_never_part_of_the_schema(registry: SkillRegistry):
    assert "token" not in blueprint_json_schema(registry)["$defs"]["notes_config"]["properties"]

    found = issues(registry, """
        - id: notes
          config: {title: Work, token: abc}
    """)
    assert "secret" in next(issue for issue in found if issue.path.endswith("config.token")).message


def test_a_required_secret_cannot_come_from_a_blueprint(registry: SkillRegistry, tmp_path: Path):
    write_skill(tmp_path, "locked", LOCKED_MANIFEST)
    registry.reload()

    found = issues(registry, "- id: locked")
    assert "can't be written in a blueprint" in found[0].message


def test_owner_only_skills_have_no_audience(registry: SkillRegistry):
    variant_schema = blueprint_json_schema(registry)["$defs"]["Skill_my_accounts"]
    assert "available_to" not in variant_schema["properties"]

    found = issues(registry, """
        - id: my_accounts
          available_to: [guest]
    """)
    assert "can't be shared" in found[0].message


def test_skill_config_is_checked_against_the_manifest(registry: SkillRegistry):
    found = issues(registry, """
        - id: notes
          config: {titel: Work, tone: loud}
    """)
    paths = {issue.path: issue for issue in found}
    assert paths["resources.helper.skills[0].config.titel"].hint == "Did you mean 'title'?"
    assert "resources.helper.skills[0].config.tone" in paths
    assert "resources.helper.skills[0].config.title" in paths


def test_unknown_skill_and_duplicate_skill(registry: SkillRegistry):
    assert issues(registry, "- id: note")[0].hint == "Did you mean 'notes'?"

    found = issues(registry, """
        - id: notes
          config: {title: A}
        - id: notes
          config: {title: B}
    """)
    assert "listed twice" in found[0].message


def test_valid_skill_entry_passes(registry: SkillRegistry):
    validated = validate_blueprint(blueprint_with("""
        - id: notes
          config: {title: Work}
          available_to: [visitor]
    """), registry=registry)
    assert validated.blueprint.resources["helper"].skills[0].available_to == ["visitor"]


def test_no_new_install_field_lacks_help_text():
    gaps = {
        f"{loaded.manifest.id}.{field.name}"
        for loaded in get_skill_registry().list()
        for field in loaded.manifest.form
        if not (field.attr or {}).get("help_text")
    }
    assert gaps - FIELDS_WITHOUT_HELP_TEXT == set(), "Give these install fields an attr.help_text"
    assert FIELDS_WITHOUT_HELP_TEXT - gaps == set(), "These now have help text; remove them from the allowlist"
