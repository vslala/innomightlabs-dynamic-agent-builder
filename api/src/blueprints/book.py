"""The blueprint book: everything Ada can build, as pages she opens when she needs them.

Every page is generated from the code that defines it, so a new resource kind, skill manifest or example
blueprint adds its page with no change here or in Ada's prompt:

- `guide/blueprint`: the document's shape, from the `Blueprint` model.
- `kind/<Kind>`: one per entry in `RESOURCE_KINDS`, from its spec model and the examples that use it.
- `skill/<id>`: one per skill manifest, from the same variants the schema and the validator use. Skills come in
  one chapter per `SkillSetup` tier (what they need before they work), easiest first.
- `recipe/<name>`: one per example blueprint, which is also one of Ada's ideas.

See docs/LLD-ada-capabilities.md.
"""

from __future__ import annotations

import re
import types
from typing import Any, Optional, Union, get_args, get_origin

import yaml  # type: ignore[import-untyped,unused-ignore]
from pydantic import BaseModel

from src.agents.book import Book, Chapter, Page
from src.blueprints.catalog import build_ideas, field_rows, markdown_table, skill_config_rows
from src.blueprints.kinds import RESOURCE_KINDS, ResourceKind
from src.blueprints.skills_schema import SkillSetup, SkillVariant, requirement_note, skill_variants
from src.blueprints.document import Blueprint
from src.blueprints.draft import Draft
from src.blueprints.spec import AVAILABLE_TO_DESCRIPTION, Metadata, OutputSpec, ParamSpec
from src.skills.disclosure import summarize
from src.skills.registry import SkillRegistry

GUIDE = "guide/blueprint"


def kind_page_id(kind: str) -> str:
    return f"kind/{kind}"


def skill_page_id(skill_id: str) -> str:
    return f"skill/{skill_id}"


def recipe_page_id(name: str) -> str:
    return f"recipe/{name}"


# --- Guides -------------------------------------------------------------------------------------------------


class GuidePages:
    def chapter(self) -> Chapter:
        sections: list[tuple[str, type[BaseModel]]] = [
            ("The document", Blueprint),
            ("metadata", Metadata),
            ("params.<name>", ParamSpec),
            ("outputs.<name>", OutputSpec),
        ]
        body = []
        for title, model in sections:
            purpose = (model.__doc__ or "").strip()
            body += [f"### {title}", *([purpose] if purpose else []), *markdown_table(field_rows(model)), ""]
        return Chapter(
            title="Guides",
            intro="How a blueprint document is laid out.",
            pages=(Page(
                id=GUIDE,
                title="Blueprint document",
                summary="The top-level fields: apiVersion, kind, metadata, params, resources, outputs.",
                use_when="Starting a blueprint from scratch, or fixing an issue outside `resources`.",
                body="\n".join(body).strip(),
            ),),
        )


# --- Resource kinds -------------------------------------------------------------------------------------------


def _nested_models(model: type[BaseModel]) -> list[type[BaseModel]]:
    """Models a spec's fields are built from (a knowledge base's `crawl`), so their fields are on the page too."""
    found: list[type[BaseModel]] = []

    def visit(annotation: Any) -> None:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            if annotation not in found:
                found.append(annotation)
            return
        if get_origin(annotation) in (Union, types.UnionType, list, dict) or get_args(annotation):
            for arg in get_args(annotation):
                visit(arg)

    for info in model.model_fields.values():
        visit(info.annotation)
    return found


def resource_text(blueprint_yaml: str, name: str) -> Optional[str]:
    """One resource as it's written in an example, comments and block text kept."""
    lines = blueprint_yaml.splitlines()
    start = next((i for i, line in enumerate(lines) if line == f"  {name}:"), None)
    if start is None:
        return None
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or lines[end].startswith("   ")):
        end += 1
    return "\n".join(line[2:] for line in lines[start:end]).rstrip()


def kind_example(kind: str) -> Optional[str]:
    """The first resource of this kind in the example blueprints."""
    for idea in build_ideas():
        resources = (yaml.safe_load(idea.yaml) or {}).get("resources", {})
        for name, spec in resources.items():
            if isinstance(spec, dict) and spec.get("kind") == kind:
                return resource_text(idea.yaml, name)
    return None


def kind_page(kind: ResourceKind[Any]) -> Page:
    model = kind.spec_model
    rows = [row for row in field_rows(model) if row["name"] != "kind"]
    body = [
        f"Write it as a resource with `kind: {kind.kind}`.",
        "",
        "### Fields",
        *markdown_table(rows),
        "",
    ]
    for nested in _nested_models(model):
        purpose = (nested.__doc__ or "").strip()
        body += [f"### {nested.__name__}", *([purpose] if purpose else []), *markdown_table(field_rows(nested)), ""]
    if "skills" in model.model_fields:
        body += ["Each skill has its own page in the Skills chapter with its settings.", ""]
    body += kind.page_sections()
    body += [f"Outputs can use: {', '.join(f'`{name}`' for name in kind.exposes)}.", ""]
    example = kind_example(kind.kind)
    if example:
        body += ["### Example", "```yaml", example, "```"]
    return Page(
        id=kind_page_id(kind.kind),
        title=kind.label,
        summary=(model.__doc__ or "").strip(),
        use_when=kind.use_when,
        body="\n".join(body).strip(),
    )


class KindPages:
    def chapter(self) -> Chapter:
        return Chapter(
            title="Resource kinds",
            intro="The things a blueprint can create or update, one page each.",
            pages=tuple(kind_page(kind) for kind in RESOURCE_KINDS),
        )


# --- Skills ---------------------------------------------------------------------------------------------------


#: Each tier's chapter: its title, and what Ada does with the skills in it.
SKILL_CHAPTERS: dict[SkillSetup, tuple[str, str]] = {
    SkillSetup.READY: (
        "Skills: ready to use",
        "Nothing to set up: add them to an Agent's `skills` and they work.",
    ),
    SkillSetup.SETTINGS: (
        "Skills: need settings",
        "Each needs settings only the person knows, listed on its page. Leave those out: when you plan, the system "
        "asks the person in a form, one skill at a time, and puts their answers in the draft.",
    ),
    SkillSetup.ACCOUNT: (
        "Skills: need a connected account",
        "Each works through an account the person connects, such as a Google sign-in. One marked NOT READY isn't "
        "connected: don't add it; tell them to connect it on the Connectors page, then add it.",
    ),
    SkillSetup.SECRETS: (
        "Skills: need a secret (not buildable yet)",
        "Each needs a secret such as an API key, which can't go in a blueprint. Don't add them; tell the person to "
        "install them from the agent's Skills tab.",
    ),
}


def skill_example(variant: SkillVariant) -> str:
    """The settings Ada writes, and none of the person's: the system asks for those."""
    manifest = variant.skill.manifest
    lines = ["skills:", f"  - id: {manifest.id}"]
    if variant.shareable:
        lines.append("    available_to: [visitor]   # only if people other than you should use it")
    if variant.builder_settings:
        lines.append("    config:")
        for field in variant.builder_settings:
            value = "<an Agent's name in this blueprint>" if field.name in variant.agent_fields else f"<{field.label}>"
            lines.append(f"      {field.name}: {value}")
    return "\n".join(lines)


def skill_note(variant: SkillVariant, ready: bool) -> str:
    """Said in the index too, so Ada knows before opening the page."""
    if variant.setup == SkillSetup.SECRETS:
        return f"Needs {', '.join(field.label for field in variant.required_secrets)}: not buildable yet."
    if not ready and variant.setup == SkillSetup.ACCOUNT:
        return "NOT READY: the person must connect an account first; don't add it, tell them."
    if not ready:
        return "NOT READY: it isn't available on InnomightLabs right now; don't add it."
    return ""


def _settings_section(variant: SkillVariant) -> list[str]:
    """Which settings Ada writes and which the system asks the person for, read from the manifest."""
    lines = []
    if variant.builder_settings:
        names = ", ".join(f"`{field.name}` ({field.label})" for field in variant.builder_settings)
        lines.append(
            f"- You write: {names}. They come from what the person asked for. A setting naming an agent takes an "
            "Agent in this blueprint by its resource name, or an agent id from list_my_agents."
        )
    if variant.person_settings and variant.setup != SkillSetup.SECRETS:
        labels = ", ".join(field.label for field in variant.person_settings)
        lines.append(
            f"- The person gives: {labels}. Leave these out of `config`: when you plan, the system asks them in a "
            "form. Don't ask for them yourself."
        )
    manifest = variant.skill.manifest
    if manifest.repeatable:
        lines.append("- It can be added more than once: list it again, and the person sets each one up.")
    return ["### Settings", *lines, ""] if lines else []


def skill_page(variant: SkillVariant, ready: bool = True) -> Page:
    manifest = variant.skill.manifest
    title, _ = SKILL_CHAPTERS[variant.setup]
    body = [
        f"Add it to an agent's `skills` as `- id: {manifest.id}`. Setup: {title.split(': ', 1)[1]}.",
        "",
        manifest.description.strip(),
        "",
    ]
    requirements = requirement_note(variant.skill)
    if requirements:
        body += [requirements, ""]
    if variant.shareable:
        body += [f"`available_to`: {AVAILABLE_TO_DESCRIPTION}", ""]
    else:
        body += ["Only the owner can use it, so it takes no `available_to`.", ""]
    body += _settings_section(variant)
    rows = skill_config_rows(variant)
    body += ["### Settings (`config`)", *(markdown_table(rows) if rows else ["None."]), ""]
    if variant.secret_fields:
        labels = [field.label for field in manifest.form if field.name in variant.secret_fields]
        body += [
            f"It also has secret settings ({', '.join(labels)}). Never write them in a blueprint; the person sets "
            "them on the agent's Skills tab.",
            "",
        ]
    note = skill_note(variant, ready)
    if note:
        body += [f"**{note}**", ""]
    body += ["### Example", "```yaml", skill_example(variant), "```"]
    return Page(
        id=skill_page_id(manifest.id),
        title=manifest.name,
        summary=summarize(manifest.description),
        body="\n".join(body).strip(),
        note=note,
        related=(kind_page_id("Agent"),),
    )


class SkillPages:
    """One tier's skills."""

    def __init__(
        self, setup: SkillSetup, registry: Optional[SkillRegistry] = None, ready: Optional[dict[str, bool]] = None
    ):
        self.setup = setup
        self.registry = registry
        self.ready = ready or {}

    def chapter(self) -> Chapter:
        title, intro = SKILL_CHAPTERS[self.setup]
        return Chapter(
            title=title,
            intro=intro,
            pages=tuple(
                skill_page(variant, self.ready.get(skill_id, True))
                for skill_id, variant in skill_variants(self.registry).items()
                if variant.setup == self.setup
            ),
        )


# --- Recipes --------------------------------------------------------------------------------------------------


class RecipePages:
    def chapter(self) -> Chapter:
        pages = []
        for idea in build_ideas():
            resources = (yaml.safe_load(idea.yaml) or {}).get("resources", {})
            kinds = dict.fromkeys(spec.get("kind") for spec in resources.values() if isinstance(spec, dict))
            pages.append(Page(
                id=recipe_page_id(idea.name),
                title=idea.title,
                summary=idea.description,
                body="\n".join([
                    "A complete blueprint to start from. Adapt it to what the person asked for.",
                    "```yaml",
                    idea.yaml.strip(),
                    "```",
                ]),
                related=tuple(kind_page_id(kind) for kind in kinds if kind),
            ))
        return Chapter(
            title="Recipes",
            intro="Complete blueprints for the things people most often build. These are also your ideas to offer.",
            pages=tuple(pages),
        )


def blueprint_book(registry: Optional[SkillRegistry] = None, ready: Optional[dict[str, bool]] = None) -> Book:
    """`ready` marks skills the person can't use yet (an account to connect), by skill id."""
    skills = [SkillPages(setup, registry, ready) for setup in SkillSetup]
    return Book.from_sources([GuidePages(), KindPages(), *skills, RecipePages()])


# --- Issues point at pages ------------------------------------------------------------------------------------

_SKILL_PATH = re.compile(r"^resources\.([^.\[]+)\.skills\[(\d+)\]")
_RESOURCE_PATH = re.compile(r"^resources\.([^.\[]+)")


def page_for_issue(path: str, draft: Draft, book: Book) -> Optional[str]:
    """The page that explains the part of the blueprint an issue is about."""
    if not draft.parsed:
        return GUIDE
    resources = draft.resources
    candidates: list[str] = []
    if skill := _SKILL_PATH.match(path):
        spec = resources.get(skill.group(1))
        entries = spec.get("skills") if spec else None
        index = int(skill.group(2))
        if isinstance(entries, list) and index < len(entries) and isinstance(entries[index], dict):
            candidates.append(skill_page_id(str(entries[index].get("id"))))
    if resource := _RESOURCE_PATH.match(path):
        spec = resources.get(resource.group(1))
        if spec:
            candidates.append(kind_page_id(str(spec.get("kind"))))
    candidates.append(GUIDE)
    return next((page_id for page_id in candidates if book.get(page_id)), None)
