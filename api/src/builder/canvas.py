"""The blueprint document Ila shows: a drawing of what she'll build, the steps, and the YAML.

Rendered twice in a build: as a draft awaiting approval when she plans, and stamped "built" with the outputs
when she applies. It's an ordinary canvas artifact, so the chat shows it inline and keeps it on the message.
The canvas is decoration: if it can't be saved, the plan and the build carry on without it.
"""

import html
import json
import logging
import re
from dataclasses import dataclass, field
from graphlib import TopologicalSorter
from pathlib import Path
from typing import Any, Literal, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from src.agents.runtime_state import AgentTurnState
from src.artifacts.models import ArtifactSource
from src.artifacts.service import ArtifactService
from src.blueprints.models import Deployment
from src.blueprints.kinds import kind_for
from src.blueprints.planner import Plan
from src.blueprints.spec import API_VERSION
from src.blueprints.validator import ValidatedBlueprint
from src.skills.html_canvas.models import CANVAS_ARTIFACT_FILENAME

log = logging.getLogger(__name__)

Stage = Literal["plan", "built"]

_env = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parent / "templates"),
    autoescape=select_autoescape(["html", "j2"]),
)


@dataclass(frozen=True)
class Card:
    name: str
    kind: str
    label: str
    title: str
    #: The resource's own `description`: what it's for, in the author's words.
    summary: str
    details: list[str]
    #: Column in the drawing: how many references deep the resource sits.
    depth: int
    #: create, update, unchanged or remove, from the plan.
    action: str = "create"
    #: For an update, what changes.
    changes: tuple[str, ...] = ()
    #: What it takes away; drawn in red, since it can't be undone.
    removals: tuple[str, ...] = ()


@dataclass(frozen=True)
class BlueprintDrawing:
    title: str
    description: str
    stage: Stage
    plan_id: str
    cards: list[Card]
    #: (from, to, label) by resource name, in the direction the drawing reads: knowledge feeds an agent, an agent
    #: hands work to another, an agent chats through a widget.
    edges: list[tuple[str, str, str]]
    steps: list[str]
    params: list[tuple[str, str]]
    yaml_html: Markup
    outputs: list[tuple[str, str, str]] = field(default_factory=list)
    api_version: str = API_VERSION


def _wires(name: str, spec: Any, resources: dict[str, Any]) -> list[tuple[str, str, str]]:
    """How this resource connects to the others it names, each wire pointing the way the drawing reads."""
    wires: list[tuple[str, str, str]] = []
    for reference in kind_for(spec.kind).references(name, spec):
        if reference.target not in resources:
            continue
        if reference.outward_wire:
            wires.append((name, reference.target, reference.outward_wire))
        else:
            wires.append((reference.target, name, kind_for(reference.kind).feeds))
    return list(dict.fromkeys(wires))


def _columns(names: list[str], wires: list[tuple[str, str, str]]) -> dict[str, int]:
    """Each resource's column: one right of everything wired into it."""
    before: dict[str, set[str]] = {name: set() for name in names}
    for source, target, _ in wires:
        before[target].add(source)
    column: dict[str, int] = {}
    for name in TopologicalSorter(before).static_order():
        column[name] = 1 + max((column[source] for source in before[name]), default=-1)
    return column


_YAML_KEY = re.compile(r"^(\s*)(- )?([A-Za-z_][\w-]*)(:)(.*)$")
_TEMPLATE = re.compile(r"\{\{.*?\}\}")
_LITERAL = re.compile(r"^\s*(true|false|null|-?\d+(\.\d+)?)\s*$")


def _value(text: str) -> str:
    if not text.strip():
        return html.escape(text, quote=False)
    if _LITERAL.match(text):
        return f'<span class="y-lit">{html.escape(text, quote=False)}</span>'
    escaped = html.escape(text, quote=False)
    return '<span class="y-val">' + _TEMPLATE.sub(lambda m: f'<span class="y-tpl">{m.group(0)}</span>', escaped) + "</span>"


def highlight_yaml(text: str) -> Markup:
    """YAML as numbered, coloured lines. Everything is escaped before any markup is added."""
    lines = []
    for number, line in enumerate(text.rstrip("\n").splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            body = f'<span class="y-com">{html.escape(line, quote=False)}</span>'
        elif match := _YAML_KEY.match(line):
            indent, dash, key, colon, rest = match.groups()
            body = (
                html.escape(indent)
                + (f'<span class="y-dash">{dash}</span>' if dash else "")
                + f'<span class="y-key">{html.escape(key)}</span>{colon}'
                + _value(rest)
            )
        else:
            leading = line[: len(line) - len(stripped)]
            if stripped.startswith("- "):
                body = html.escape(leading) + '<span class="y-dash">- </span>' + _value(stripped[2:])
            else:
                body = html.escape(leading) + _value(stripped)
        lines.append(f'<span class="y-line"><span class="y-num">{number}</span>{body}</span>')
    # Each line is a block, so no newlines between them inside the <pre>.
    return Markup("".join(lines))


def drawing_for(
    validated: ValidatedBlueprint,
    plan: Plan,
    *,
    stage: Stage,
    plan_id: str,
    deployment: Optional[Deployment] = None,
) -> BlueprintDrawing:
    blueprint = validated.blueprint
    edges = [wire for name in validated.order for wire in _wires(name, blueprint.resources[name], blueprint.resources)]
    # What this plan deletes isn't in the blueprint any more; it's drawn too, marked for removal, with no wires.
    removed = {name: spec for name, spec in plan.removed_specs.items() if name not in blueprint.resources}
    names = [*validated.order, *removed]
    shown = {**blueprint.resources, **removed}
    depth = _columns(names, edges)
    cards = []
    for name in names:
        spec = shown[name]
        kind = kind_for(spec.kind)
        change = plan.changes.get(name)
        cards.append(Card(
            name=name,
            kind=spec.kind,
            label=kind.label,
            title=kind.title(name, spec, shown),
            summary=spec.description or "",
            details=kind.card_details(spec),
            depth=depth[name],
            action=change.action.value if change else "create",
            changes=change.changes if change else (),
            removals=change.removals if change else (),
        ))
    params = [
        (blueprint.params[key].label, str(value))
        for key, value in validated.params.items()
        if key in blueprint.params
    ]
    outputs = [
        (name, output.description or "", output.value)
        for name, output in (deployment.outputs.items() if deployment else [])
    ]
    return BlueprintDrawing(
        title=blueprint.metadata.title,
        description=blueprint.metadata.description or "",
        stage=stage,
        plan_id=plan_id,
        cards=cards,
        edges=edges,
        steps=[step.summary for step in plan.steps],
        params=params,
        yaml_html=highlight_yaml(validated.yaml),
        outputs=outputs,
    )


def render_drawing(drawing: BlueprintDrawing) -> str:
    edges_json = json.dumps(drawing.edges).replace("</", "<\\/")
    return _env.get_template("blueprint_canvas.html.j2").render(d=drawing, edges_json=Markup(edges_json))


def save_blueprint_canvas(drawing: BlueprintDrawing, state: AgentTurnState) -> Optional[dict[str, Any]]:
    """A `canvas_artifact` payload, or None if it couldn't be saved."""
    try:
        artifact = ArtifactService().create_artifact(
            owner_email=state.owner_email,
            artifact_type="canvas",
            title=f"{'Built' if drawing.stage == 'built' else 'Blueprint'}: {drawing.title}",
            filename=CANVAS_ARTIFACT_FILENAME,
            mime_type="text/html",
            body=render_drawing(drawing).encode("utf-8"),
            source=ArtifactSource(
                agent_id=state.agent_id,
                conversation_id=state.conversation_id,
                message_id=state.user_message_id,
                metadata={"source": "ila", "stage": drawing.stage, "plan_id": drawing.plan_id},
            ),
        )
    except Exception:
        log.warning("Couldn't save the blueprint canvas for %s", state.conversation_id, exc_info=True)
        return None
    return {
        "ok": True,
        "type": "canvas_artifact",
        "artifact_id": artifact.artifact_id,
        "title": artifact.title,
        "mime_type": artifact.mime_type,
    }
