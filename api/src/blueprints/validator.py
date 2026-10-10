"""Validating a blueprint: structure, params, templates, references and skills.

Every problem becomes a BlueprintIssue with a path, a line and, where possible, a hint, and all of
them are reported together, so a person or a model can fix a blueprint in one pass.
"""

import difflib
import re
from dataclasses import dataclass, field
from graphlib import CycleError, TopologicalSorter
from typing import Any, Iterable, Iterator, Optional

from pydantic import BaseModel, ValidationError

from src.blueprints.issues import BlueprintInvalid, BlueprintIssue, IssueOwner
from src.blueprints.document import Blueprint
from src.blueprints.kinds import KIND_NAMES, RESOURCE_KINDS, kind_for
from src.blueprints.params import param_type
from src.blueprints.parser import join_path, parse_yaml
from src.blueprints.references import Reference
from src.blueprints.skills_schema import SkillSetup, SkillVariant, skill_variants
from src.blueprints.spec import (
    AgentSpec,
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

STRUCTURE_MODELS: tuple[type[BaseModel], ...] = (
    Blueprint, Metadata, ParamSpec, CrawlSpec, SkillEntry, OutputSpec, *(kind.spec_model for kind in RESOURCE_KINDS),
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
        kind = param_type(spec)
        if kind.takes_options and not spec.options:
            issues.append(BlueprintIssue(path=f"{path}.options", message=f"A `{kind.name}` param needs `options`."))
        if not kind.takes_options and spec.options:
            issues.append(BlueprintIssue(path=f"{path}.options", message="Only `choice` params have `options`."))
        if spec.default is not None:
            _, error = kind.coerce(spec, spec.default)
            if error:
                issues.append(BlueprintIssue(path=f"{path}.default", message=f"The default {error}"))
    return issues


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
        value, error = param_type(spec).coerce(spec, raw)
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
    """Every reference a kind lists must name a resource of the right kind. Returns the apply order."""
    issues = []
    graph: dict[str, set[str]] = {}
    for name, resource in blueprint.resources.items():
        depends_on: set[str] = set()
        for reference in kind_for(resource.kind).references(name, resource):
            referenced = blueprint.resources.get(reference.target)
            if referenced is None:
                if not reference.may_be_id:  # an id is checked against the account by the plan
                    issues.append(BlueprintIssue(
                        path=reference.path,
                        message=f"'{reference.target}' is not a resource in this blueprint.",
                        hint=did_you_mean(reference.target, blueprint.resources.keys()),
                    ))
                continue
            problem = _reference_problem(name, resource, reference, referenced)
            if problem:
                issues.append(problem)
            else:
                depends_on.add(reference.target)
        graph[name] = depends_on
    try:
        order = list(TopologicalSorter(graph).static_order())
    except CycleError as e:
        cycle = " → ".join(e.args[1])
        issues.append(BlueprintIssue(path="resources", message=f"These resources refer to each other in a loop: {cycle}."))
        order = []
    return issues, order


def _a(word: str) -> str:
    return f"an {word}" if word[:1].lower() in "aeiou" else f"a {word}"


def _reference_problem(name: str, resource: Any, reference: Reference, referenced: Any) -> Optional[BlueprintIssue]:
    if reference.target == name:
        return BlueprintIssue(
            path=reference.path,
            message=f"{reference.where[:1].upper()}{reference.where[1:]} can't name the "
            f"{kind_for(resource.kind).label.lower()} itself.",
        )
    if referenced.kind != reference.kind:
        return BlueprintIssue(
            path=reference.path,
            message=f"'{reference.target}' is {_a(referenced.kind)}, not {_a(reference.kind)}.",
            hint=f"{reference.where[:1].upper()}{reference.where[1:]} needs {_a(reference.kind)}.",
        )
    return None


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
            required_secrets = [field_def.label for field_def in variant.required_secrets]
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
                theirs = _person_settings_missing(variant, path, config)
                issues += [
                    issue.model_copy(update={"owner": IssueOwner.PERSON}) if issue.path in theirs else issue
                    for issue in issues_from_validation_error(e, path, vocabulary)
                ]
            if skill_id in installed and not manifest.repeatable:
                issues.append(BlueprintIssue(
                    path=f"{path}.id",
                    message=f"{manifest.name} is listed twice, and an agent can have it only once.",
                ))
            installed.add(skill_id)
    return issues


def _person_settings_missing(variant: SkillVariant, path: str, config: dict[str, Any]) -> set[str]:
    """Paths of the required settings only the person knows that this entry doesn't have yet. Issues there are the
    person's to settle (the builder asks them in a form), not the author's to fix. A skill that needs a secret
    can't be built yet, so nobody is asked."""
    if variant.setup == SkillSetup.SECRETS:
        return set()
    missing = {f"{path}.config.{field.name}" for field in variant.person_settings if config.get(field.name) in (None, "")}
    # With nothing written under `config`, the issue is about `config` itself.
    return missing | ({f"{path}.config"} if missing and not config else set())
