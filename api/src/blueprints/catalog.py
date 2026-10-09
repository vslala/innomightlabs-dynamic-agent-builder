"""Views of the one schema: the published JSON Schema, a Markdown reference, the Builder's catalog,
and the run form for a blueprint's params. None of them is written by hand."""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Optional, Union

import yaml  # type: ignore[import-untyped,unused-ignore]
from pydantic import BaseModel, Field, TypeAdapter

import src.form_models as form_models
from src.blueprints.kinds import RESOURCE_KINDS
from src.blueprints.params import param_type
from src.blueprints.skills_schema import SkillVariant, describe_field, skill_variants
from src.blueprints.document import Blueprint
from src.blueprints.spec import API_VERSION, CrawlSpec, Metadata, OutputSpec, ParamSpec, SkillEntry
from src.skills.registry import SkillRegistry

EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"
SCHEMA_ID = "https://api.innomightlabs.com/blueprints/schema/v2.json"


def example_names() -> list[str]:
    return sorted(path.stem for path in EXAMPLES_DIR.glob("*.yaml"))


def example_yaml(name: str) -> Optional[str]:
    if name not in example_names():
        return None
    return (EXAMPLES_DIR / f"{name}.yaml").read_text(encoding="utf-8")


@dataclass(frozen=True)
class BuildIdea:
    """Something Ada can offer to build: an example blueprint and how it describes itself."""

    name: str
    title: str
    description: str
    yaml: str


def build_ideas() -> list[BuildIdea]:
    """One idea per example blueprint, read from its own metadata, so adding an example adds an idea."""
    ideas = []
    for name in example_names():
        text = example_yaml(name) or ""
        metadata = (yaml.safe_load(text) or {}).get("metadata", {})
        ideas.append(BuildIdea(
            name=name,
            title=str(metadata.get("title") or name),
            description=str(metadata.get("description") or ""),
            yaml=text,
        ))
    return ideas


def blueprint_json_schema(registry: Optional[SkillRegistry] = None) -> dict[str, Any]:
    """The spec models, with `skills[]` replaced by one variant per skill manifest."""
    schema = Blueprint.model_json_schema(by_alias=True, ref_template="#/$defs/{model}")
    variants = [variant.model for variant in skill_variants(registry).values()]
    if variants:
        if len(variants) == 1:
            adapter: TypeAdapter[Any] = TypeAdapter(variants[0])
        else:
            adapter = TypeAdapter(Annotated[Union[tuple(variants)], Field(discriminator="id")])
        skills_schema = adapter.json_schema(ref_template="#/$defs/{model}")
        schema.setdefault("$defs", {}).update(skills_schema.pop("$defs", {}))
        schema["$defs"]["SkillEntry"] = skills_schema
    schema["$id"] = SCHEMA_ID
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = f"InnomightLabs blueprint ({API_VERSION})"
    return schema


def field_rows(model: type[BaseModel]) -> list[dict[str, Any]]:
    schema = model.model_json_schema(by_alias=True)
    required = set(schema.get("required", []))
    return [
        {
            "name": name,
            "type": _type_label(prop),
            "required": name in required,
            "description": prop.get("description", ""),
        }
        for name, prop in schema.get("properties", {}).items()
    ]


def _type_label(prop: dict[str, Any]) -> str:
    if "enum" in prop:
        return " | ".join(str(value) for value in prop["enum"])
    if "const" in prop:
        return str(prop["const"])
    if "anyOf" in prop:
        return " | ".join(_type_label(option) for option in prop["anyOf"] if option.get("type") != "null")
    if "$ref" in prop:
        return str(prop["$ref"]).rsplit("/", 1)[-1]
    if prop.get("type") == "array":
        return f"list of {_type_label(prop.get('items', {}))}"
    return str(prop.get("type", "any"))


def skill_config_rows(variant: SkillVariant) -> list[dict[str, Any]]:
    return [
        {
            "name": field_def.name,
            "type": field_def.input_type.value,
            "required": not field_def.is_optional and field_def.value is None,
            "description": describe_field(field_def),
        }
        for field_def in variant.skill.manifest.form
        if field_def.name not in variant.secret_fields
    ]


def catalog(registry: Optional[SkillRegistry] = None, ready: Optional[dict[str, bool]] = None) -> dict[str, Any]:
    """What the Builder model reads: every kind and every skill, in a compact form."""
    return {
        "api_version": API_VERSION,
        "kinds": [
            {
                "kind": kind.kind,
                "purpose": (kind.spec_model.__doc__ or "").strip(),
                "fields": [row for row in field_rows(kind.spec_model) if row["name"] != "kind"],
                "exposes": list(kind.exposes),
            }
            for kind in RESOURCE_KINDS
        ],
        "skills": [
            {
                "id": skill_id,
                "name": variant.skill.manifest.name,
                "description": variant.skill.manifest.description,
                "config_fields": skill_config_rows(variant),
                "shareable": variant.shareable,
                "actions": [
                    {"name": action.name, "description": action.description}
                    for action in variant.skill.manifest.actions
                ],
                **({"ready": ready.get(skill_id, True)} if ready is not None else {}),
            }
            for skill_id, variant in skill_variants(registry).items()
        ],
        "examples": example_names(),
    }


def markdown_table(rows: list[dict[str, Any]]) -> list[str]:
    lines = ["| Field | Type | Required | Description |", "| --- | --- | --- | --- |"]
    for row in rows:
        description = row["description"].replace("|", "\\|").replace("\n", " ")
        kind = row["type"].replace("|", "\\|")
        lines.append(f"| `{row['name']}` | {kind} | {'yes' if row['required'] else 'no'} | {description} |")
    return lines


def _section(title: str, model: type[BaseModel]) -> list[str]:
    purpose = (model.__doc__ or "").strip()
    return [f"## {title}", "", *([purpose, ""] if purpose else []), *markdown_table(field_rows(model)), ""]


def reference_markdown(registry: Optional[SkillRegistry] = None) -> str:
    """The human reference, rendered from the schema so it can't fall out of step."""
    out = [
        f"# Blueprint reference ({API_VERSION})",
        "",
        "Generated from the blueprint spec and the installed skill manifests.",
        "",
        "## Blueprint",
        "",
        *markdown_table(field_rows(Blueprint)),
        "",
        *_section("Metadata", Metadata),
        *_section("Param", ParamSpec),
        *_section("Output", OutputSpec),
    ]
    for entry in catalog(registry)["kinds"]:
        out += [f"## {entry['kind']}", "", entry["purpose"], "", *markdown_table(entry["fields"]), ""]
        out += [f"Outputs can use: {', '.join(f'`{name}`' for name in entry['exposes'])}.", ""]
    out += [*_section("Crawl", CrawlSpec), *_section("Skill entry", SkillEntry)]
    out += ["## Skills", ""]
    for skill in catalog(registry)["skills"]:
        out += [f"### `{skill['id']}`: {skill['name']}", "", skill["description"], ""]
        if not skill["shareable"]:
            out += ["Only you can use this skill, so it takes no `available_to`.", ""]
        if skill["config_fields"]:
            out += [*markdown_table(skill["config_fields"]), ""]
    return "\n".join(out)


def params_form(blueprint: Blueprint) -> form_models.Form:
    """The blueprint's params as a schema-driven form, so the SPA renders them with SchemaForm."""
    inputs = []
    for name, spec in blueprint.params.items():
        kind = param_type(spec)
        attr = {}
        if spec.description:
            attr["help_text"] = spec.description
        if spec.default is not None:
            attr["optional"] = "true"
        if kind.placeholder:
            attr["placeholder"] = kind.placeholder
        default = spec.default
        inputs.append(form_models.FormInput(
            input_type=kind.input_type,
            name=name,
            label=spec.label,
            value=str(default).lower() if isinstance(default, bool) else None if default is None else str(default),
            values=kind.form_values(spec),
            attr=attr or None,
        ))
    return form_models.Form(form_name=blueprint.metadata.title, submit_path="/blueprints/plan", form_inputs=inputs)
