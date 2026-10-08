"""Validating a blueprint: structure, params, templates, references and skills.

Every problem becomes a BlueprintIssue with a path, a line and, where possible, a hint, and all of
them are reported together, so a person or a model can fix a blueprint in one pass.
"""

import difflib
import re
from dataclasses import dataclass, field
from graphlib import CycleError, TopologicalSorter
from typing import Any, Iterable, Iterator, Optional, get_args

from pydantic import BaseModel, ValidationError

from src.blueprints.issues import BlueprintInvalid, BlueprintIssue
from src.blueprints.kinds import kind_for
from src.blueprints.parser import join_path, parse_yaml
from src.blueprints.skills_schema import SkillVariant, skill_variants
from src.blueprints.spec import (
    REF_KIND,
    REMOVES,
    RESOURCE_SPECS,
    AgentSpec,
    Blueprint,
    CrawlSpec,
    Metadata,
    OutputSpec,
    ParamSpec,
    SkillEntry,
)
from src.config import settings
from src.skills.registry import SkillRegistry

TEMPLATE = re.compile(r"\{\{\s*(.*?)\s*\}\}")
PARAM_REF = re.compile(r"^params\.([A-Za-z0-9_]+)$")
RESOURCE_REF = re.compile(r"^resources\.([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)$")
URL = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.IGNORECASE)
TRUE_WORDS = {"true", "yes", "on", "1"}
FALSE_WORDS = {"false", "no", "off", "0"}

KIND_NAMES = [get_args(spec.model_fields["kind"].annotation)[0] for spec in RESOURCE_SPECS]
STRUCTURE_MODELS: tuple[type[BaseModel], ...] = (
    Blueprint, Metadata, ParamSpec, CrawlSpec, SkillEntry, OutputSpec, *RESOURCE_SPECS,
)
VOCABULARY = sorted({
    field_info.alias or name for model in STRUCTURE_MODELS for name, field_info in model.model_fields.items()
})


@dataclass
class ValidatedBlueprint:
    blueprint: Blueprint
    yaml: str
    #: Resolved param values; empty when validated without params.
    params: dict[str, Any] = field(default_factory=dict)
    #: Resource names in the order they must be created.
    order: list[str] = field(default_factory=list)


def did_you_mean(word: str, candidates: Iterable[str]) -> Optional[str]:
    matches = difflib.get_close_matches(str(word), list(candidates), n=1, cutoff=0.6)
    return f"Did you mean '{matches[0]}'?" if matches else None


def validate_blueprint(
    text: str,
    params: Optional[dict[str, Any]] = None,
    *,
    registry: Optional[SkillRegistry] = None,
) -> ValidatedBlueprint:
    """With `params`, also resolves them into the blueprint. Raises BlueprintInvalid with every issue found."""
    data, lines = parse_yaml(text)
    if not isinstance(data, dict):
        raise BlueprintInvalid([BlueprintIssue(path="", line=1, message="A blueprint must be a YAML mapping.")])

    issues = list(check_templates(data))
    template = _model_or_issues(data, lines, issues)
    if template is None:
        raise BlueprintInvalid(_with_lines(issues, lines))
    issues += check_param_specs(template)

    blueprint = template
    values: dict[str, Any] = {}
    if params is not None and not issues:
        values, param_issues = resolve_params(template.params, params)
        issues += param_issues
        if not param_issues:
            data = substitute(data, values)
            substituted = _model_or_issues(data, lines, issues)
            if substituted is None:
                raise BlueprintInvalid(_with_lines(issues, lines))
            blueprint = substituted

    if len(blueprint.resources) > settings.blueprint_max_resources:
        issues.append(BlueprintIssue(
            path="resources",
            message=f"A blueprint can create at most {settings.blueprint_max_resources} resources.",
        ))
    issues += check_skills(blueprint, data, skill_variants(registry))
    for name, resource in blueprint.resources.items():
        issues += kind_for(resource.kind).validate(name, resource)
    reference_issues, order = check_references(blueprint)
    issues += reference_issues
    issues += check_removals(blueprint, skill_variants(registry))

    if issues:
        raise BlueprintInvalid(_with_lines(issues, lines))
    return ValidatedBlueprint(blueprint=blueprint, yaml=text, params=values, order=order)


def _model_or_issues(data: dict[str, Any], lines: dict[str, int], issues: list[BlueprintIssue]) -> Optional[Blueprint]:
    try:
        return Blueprint.model_validate(data)
    except ValidationError as e:
        issues += issues_from_validation_error(e, "", VOCABULARY)
        return None


def issues_from_validation_error(error: ValidationError, prefix: str, vocabulary: Iterable[str]) -> list[BlueprintIssue]:
    issues = []
    for detail in error.errors():
        loc: list[Any] = list(detail["loc"])
        # A discriminated union adds the resource's kind to the location; it isn't part of the document.
        if len(loc) >= 3 and loc[0] == "resources" and loc[2] in KIND_NAMES:
            del loc[2]
        bad_key = "[key]" in loc
        loc = [part for part in loc if part != "[key]"]
        path = prefix
        for part in loc:
            path = join_path(path, part)
        last = loc[-1] if loc else ""
        error_type = detail["type"]
        hint = None
        if bad_key:
            message = f"'{last}' isn't a valid name. Use lowercase letters, digits and underscores, starting with a letter."
        elif error_type == "extra_forbidden":
            message = f"Unknown field '{last}'."
            hint = did_you_mean(last, vocabulary)
        elif error_type == "missing":
            message = f"'{last}' is required."
        elif error_type == "union_tag_invalid":
            given = detail.get("ctx", {}).get("tag", detail.get("input"))
            message = f"Unknown kind '{given}'. Use one of: {', '.join(KIND_NAMES)}."
            hint = did_you_mean(str(given), KIND_NAMES)
        elif error_type == "union_tag_not_found":
            message = f"Every resource needs a `kind`: one of {', '.join(KIND_NAMES)}."
        else:
            message = detail["msg"]
        issues.append(BlueprintIssue(path=path, message=message, hint=hint))
    return issues


def _with_lines(issues: list[BlueprintIssue], lines: dict[str, int]) -> list[BlueprintIssue]:
    located = []
    for issue in issues:
        line = issue.line
        path = issue.path
        # A missing field has no line of its own, so fall back to its nearest parent's.
        while line is None and path:
            line = lines.get(path)
            parent = re.sub(r"(\.[^.\[]+|\[\d+\])$", "", path)
            path = parent if parent != path else ""
        located.append(issue.model_copy(update={"line": line}))
    return located


def strings_in(value: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from strings_in(item, join_path(path, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from strings_in(item, join_path(path, index))


def check_templates(data: dict[str, Any]) -> list[BlueprintIssue]:
    """Every {{ }} must name a declared param, or, in outputs only, an attribute a resource exposes."""
    params = data.get("params")
    declared = set(params) if isinstance(params, dict) else set()
    raw_resources = data.get("resources")
    resources: dict[str, Any] = raw_resources if isinstance(raw_resources, dict) else {}
    issues = []
    for path, text in strings_in(data):
        for match in TEMPLATE.finditer(text):
            expression = match.group(1)
            param = PARAM_REF.match(expression)
            resource = RESOURCE_REF.match(expression)
            if param:
                if param.group(1) not in declared:
                    issues.append(BlueprintIssue(
                        path=path,
                        message=f"'{param.group(1)}' isn't a param of this blueprint.",
                        hint=did_you_mean(param.group(1), declared) or "Declare it under `params`.",
                    ))
            elif resource:
                if not path.startswith("outputs."):
                    issues.append(BlueprintIssue(
                        path=path,
                        message="{{ resources.… }} can only be used in `outputs`.",
                        hint="Resources refer to each other by name, e.g. `agent: assistant`.",
                    ))
                    continue
                target, attribute = resource.groups()
                spec = resources.get(target)
                if not isinstance(spec, dict):
                    issues.append(BlueprintIssue(
                        path=path,
                        message=f"'{target}' is not a resource in this blueprint.",
                        hint=did_you_mean(target, resources.keys()),
                    ))
                    continue
                if spec.get("kind") in KIND_NAMES:
                    exposes = kind_for(spec["kind"]).exposes
                    if attribute not in exposes:
                        issues.append(BlueprintIssue(
                            path=path,
                            message=f"A {spec['kind']} has no attribute '{attribute}'. It has: {', '.join(exposes)}.",
                            hint=did_you_mean(attribute, exposes),
                        ))
            else:
                issues.append(BlueprintIssue(
                    path=path,
                    message=f"'{{{{ {expression} }}}}' isn't something a blueprint can fill in.",
                    hint="Use {{ params.<name> }}, or {{ resources.<name>.<attribute> }} in outputs.",
                ))
    return issues


def check_param_specs(blueprint: Blueprint) -> list[BlueprintIssue]:
    issues = []
    for name, spec in blueprint.params.items():
        path = f"params.{name}"
        if spec.type == "choice" and not spec.options:
            issues.append(BlueprintIssue(path=f"{path}.options", message="A `choice` param needs `options`."))
        if spec.type != "choice" and spec.options:
            issues.append(BlueprintIssue(path=f"{path}.options", message="Only `choice` params have `options`."))
        if spec.default is not None:
            _, error = coerce_param(spec, spec.default)
            if error:
                issues.append(BlueprintIssue(path=f"{path}.default", message=f"The default {error}"))
    return issues


def coerce_param(spec: ParamSpec, value: Any) -> tuple[Any, Optional[str]]:
    """The value as the param's type, or an error that reads after "The value …"."""
    if spec.type == "integer":
        try:
            return int(str(value).strip()), None
        except ValueError:
            return None, "must be a whole number."
    if spec.type == "boolean":
        if isinstance(value, bool):
            return value, None
        word = str(value).strip().lower()
        if word in TRUE_WORDS | FALSE_WORDS:
            return word in TRUE_WORDS, None
        return None, "must be true or false."
    text = str(value).strip() if spec.type != "text" else str(value)
    if spec.type == "url" and not URL.match(text):
        return None, "must be a web address starting with http:// or https://."
    if spec.type == "choice" and text not in spec.options:
        return None, f"must be one of: {', '.join(spec.options)}."
    return text, None


def resolve_params(specs: dict[str, ParamSpec], given: dict[str, Any]) -> tuple[dict[str, Any], list[BlueprintIssue]]:
    values: dict[str, Any] = {}
    issues = []
    for name in given:
        if name not in specs:
            issues.append(BlueprintIssue(
                path=f"params.{name}",
                message=f"'{name}' isn't a param of this blueprint.",
                hint=did_you_mean(name, specs.keys()),
            ))
    for name, spec in specs.items():
        raw = given.get(name)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            raw = spec.default
        if raw is None:
            issues.append(BlueprintIssue(path=f"params.{name}", message=f"'{spec.label}' is required."))
            continue
        value, error = coerce_param(spec, raw)
        if error:
            issues.append(BlueprintIssue(path=f"params.{name}", message=f"'{spec.label}' {error}"))
        else:
            values[name] = value
    return values, issues


def substitute(value: Any, params: dict[str, Any]) -> Any:
    """Fills {{ params.x }} in every string. {{ resources.… }} is left for apply."""
    if isinstance(value, str):
        def fill(match: re.Match[str]) -> str:
            param = PARAM_REF.match(match.group(1))
            return str(params[param.group(1)]) if param and param.group(1) in params else match.group(0)
        return TEMPLATE.sub(fill, value)
    if isinstance(value, dict):
        return {key: substitute(item, params) for key, item in value.items()}
    if isinstance(value, list):
        return [substitute(item, params) for item in value]
    return value


def check_references(blueprint: Blueprint) -> tuple[list[BlueprintIssue], list[str]]:
    """Reference fields (marked with x-ref-kind) must name a resource of the right kind. Returns the apply order."""
    issues = []
    graph: dict[str, set[str]] = {}
    for name, resource in blueprint.resources.items():
        depends_on: set[str] = set()
        for field_name, field_info in type(resource).model_fields.items():
            extra = field_info.json_schema_extra
            if not isinstance(extra, dict) or REF_KIND not in extra:
                continue
            value = getattr(resource, field_name)
            targets = value if isinstance(value, list) else [value]
            for index, target in enumerate(targets):
                path = f"resources.{name}.{field_name}"
                if isinstance(value, list):
                    path = join_path(path, index)
                referenced = blueprint.resources.get(target)
                if referenced is None:
                    issues.append(BlueprintIssue(
                        path=path,
                        message=f"'{target}' is not a resource in this blueprint.",
                        hint=did_you_mean(target, blueprint.resources.keys()),
                    ))
                elif referenced.kind != extra[REF_KIND]:
                    issues.append(BlueprintIssue(
                        path=path,
                        message=f"'{target}' is a {referenced.kind}, but `{field_name}` needs a {extra[REF_KIND]}.",
                    ))
                elif referenced.remove and not resource.remove and not extra.get(REMOVES):
                    issues.append(BlueprintIssue(
                        path=path,
                        message=f"'{target}' is being removed, so `{field_name}` can't use it.",
                        hint=f"Take '{target}' out of `{field_name}`, or don't remove it.",
                    ))
                else:
                    depends_on.add(target)
        graph[name] = depends_on
    try:
        order = list(TopologicalSorter(graph).static_order())
    except CycleError as e:
        cycle = " → ".join(e.args[1])
        issues.append(BlueprintIssue(path="resources", message=f"These resources refer to each other in a loop: {cycle}."))
        order = []
    return issues, order


def check_removals(blueprint: Blueprint, variants: dict[str, SkillVariant]) -> list[BlueprintIssue]:
    """Removing is explicit and names exactly what goes, so nothing is removed by a typo or a guess."""
    issues = []
    for name, resource in blueprint.resources.items():
        path = f"resources.{name}"
        if resource.remove and not resource.id:
            issues.append(BlueprintIssue(
                path=f"{path}.remove",
                message="Only an existing resource can be removed, and it needs its `id` to say which one.",
                hint="Load it first, so the draft has its id.",
            ))
        if not isinstance(resource, AgentSpec):
            continue
        for index, kb_name in enumerate(resource.remove_knowledge_bases):
            if kb_name in resource.knowledge_bases:
                issues.append(BlueprintIssue(
                    path=f"{path}.remove_knowledge_bases[{index}]",
                    message=f"'{kb_name}' is in both `knowledge_bases` and `remove_knowledge_bases`.",
                    hint="Keep it in one of them.",
                ))
        listed = {entry.id for entry in resource.skills}
        for index, skill_id in enumerate(resource.remove_skills):
            entry_path = f"{path}.remove_skills[{index}]"
            if skill_id not in variants:
                issues.append(BlueprintIssue(
                    path=entry_path,
                    message=f"There's no skill called '{skill_id}'.",
                    hint=did_you_mean(skill_id, variants.keys()),
                ))
            elif skill_id in listed:
                issues.append(BlueprintIssue(
                    path=entry_path,
                    message=f"'{skill_id}' is in both `skills` and `remove_skills`.",
                    hint="Keep it in one of them. To switch it off but keep it, use `enabled: false` under `skills`.",
                ))
    for output_name, output in blueprint.outputs.items():
        for token in TEMPLATE.findall(output.value):
            reference = RESOURCE_REF.match(token)
            target_name = reference.group(1) if reference else ""
            target = blueprint.resources.get(target_name)
            if target is not None and target.remove:
                issues.append(BlueprintIssue(
                    path=f"outputs.{output_name}.value",
                    message=f"'{target_name}' is being removed, so an output can't show it.",
                    hint="Remove this output.",
                ))
    return issues


def check_skills(blueprint: Blueprint, data: dict[str, Any], variants: dict[str, SkillVariant]) -> list[BlueprintIssue]:
    """Each skill entry against the variant generated from that skill's manifest."""
    issues = []
    for name, resource in blueprint.resources.items():
        if not isinstance(resource, AgentSpec):
            continue
        raw_entries = data["resources"][name].get("skills") or []
        installed: set[str] = set()
        for index, raw in enumerate(raw_entries):
            path = f"resources.{name}.skills[{index}]"
            skill_id = raw.get("id")
            variant = variants.get(skill_id)
            if variant is None:
                issues.append(BlueprintIssue(
                    path=f"{path}.id",
                    message=f"There's no skill called '{skill_id}'.",
                    hint=did_you_mean(skill_id, variants.keys()),
                ))
                continue
            manifest = variant.skill.manifest
            entry = dict(raw)
            if not variant.shareable:
                if entry.pop("available_to", None):
                    issues.append(BlueprintIssue(
                        path=f"{path}.available_to",
                        message=f"{manifest.name} uses your own accounts or access, so it can't be shared.",
                        hint="Remove `available_to`.",
                    ))
            config = dict(entry.get("config") or {})
            for secret in variant.secret_fields:
                if secret in config:
                    issues.append(BlueprintIssue(
                        path=f"{path}.config.{secret}",
                        message=f"'{secret}' is a secret, and secrets never go in a blueprint.",
                        hint="Remove it, and set it on the agent's Skills tab after apply.",
                    ))
                    config.pop(secret)
            required_secrets = [
                field_def.label for field_def in manifest.form
                if field_def.name in variant.secret_fields and not field_def.is_optional and field_def.value is None
            ]
            if required_secrets:
                issues.append(BlueprintIssue(
                    path=f"{path}.id",
                    message=f"{manifest.name} needs {', '.join(required_secrets)}, which can't be written in a blueprint.",
                    hint=f"Remove {manifest.id} here and install it from the agent's Skills tab after apply.",
                ))
            if "config" in entry:
                entry["config"] = config
            try:
                variant.model.model_validate(entry)
            except ValidationError as e:
                vocabulary = [*variant.config_fields, "id", "config", "enabled", "available_to"]
                issues += issues_from_validation_error(e, path, vocabulary)
            if skill_id in installed and not manifest.repeatable:
                issues.append(BlueprintIssue(
                    path=f"{path}.id",
                    message=f"{manifest.name} is listed twice, and an agent can have it only once.",
                ))
            installed.add(skill_id)
    return issues
