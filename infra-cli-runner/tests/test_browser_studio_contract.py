"""The Browser Studio skill's manifest (in `api/`) is what an agent is told it may send; the models here decide what is
accepted. They are written twice, by hand, so this test is what keeps them from drifting: every property, required field
and enumeration the manifest offers must be one these models have."""

from __future__ import annotations

import typing
import unittest
from pathlib import Path

import yaml

from src.infra_cli_runner.media.models import (
    FRAME_RATES,
    AudioBed,
    Clip,
    CompositionRequest,
    Output,
    Overlay,
    ProbeRequest,
    Transition,
    TransitionKind,
    ZoomKeyframe,
)
from src.infra_cli_runner.studio.models import (
    InspectRequest,
    SceneParams,
    SceneRequest,
    SceneTemplateName,
    Step,
    Target,
    Viewport,
    WalkthroughRequest,
)

MANIFEST = Path(__file__).resolve().parents[2] / "api/src/skills/browser_studio/manifest.yml"
#: Filled in by the skill from the conversation, never offered to the agent.
INJECTED = {"request_id", "workspace_id"}


def fields(model: type, *, minus: set[str] = frozenset()) -> set[str]:  # type: ignore[assignment]
    return set(model.model_fields) - minus  # type: ignore[attr-defined]


def required(model: type, *, minus: set[str] = frozenset()) -> set[str]:  # type: ignore[assignment]
    return {name for name, field in model.model_fields.items() if field.is_required()} - minus  # type: ignore[attr-defined]


def literal(annotation: object) -> set[object]:
    return set(typing.get_args(annotation))


STEP_MODELS = typing.get_args(typing.get_args(Step)[0])


@unittest.skipUnless(MANIFEST.exists(), "the API's manifest is not in this checkout")
class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        manifest = yaml.safe_load(MANIFEST.read_text())
        cls.schemas = {action["name"]: action["input_schema"] for action in manifest["actions"]}

    def properties(self, *path: str) -> dict:
        node = self.schemas[path[0]]
        for key in path[1:]:
            node = node["items"] if key == "[]" else node["properties"][key]
        return node["properties"]

    def check(self, model: type, *path: str, minus: set[str] = frozenset(), need: bool = True) -> None:  # type: ignore[assignment]
        node = self.schemas[path[0]]
        for key in path[1:]:
            node = node["items"] if key == "[]" else node["properties"][key]
        self.assertEqual(set(node["properties"]), fields(model, minus=minus), " > ".join(path))
        if need and "required" in node or need and required(model, minus=minus):
            self.assertEqual(set(node.get("required", [])), required(model, minus=minus), " > ".join(path))

    def test_each_action_offers_what_its_request_accepts(self) -> None:
        for action, model in (
            ("inspect_page", InspectRequest), ("record_walkthrough", WalkthroughRequest), ("render_scene", SceneRequest),
            ("compose_video", CompositionRequest), ("probe_media", ProbeRequest),
        ):
            self.check(model, action, minus=INJECTED)

    def test_steps_offer_every_step_there_is(self) -> None:
        union = {name for model in STEP_MODELS for name in model.model_fields}
        for action in ("record_walkthrough",):
            step = self.properties(action, "steps", "[]")
            self.assertEqual(set(step), union)
            self.assertEqual(set(step["action"]["enum"]), {literal(model.model_fields["action"].annotation).pop() for model in STEP_MODELS})
            self.assertEqual(set(self.schemas[action]["properties"]["steps"]["items"]["required"]), {"action"})
            self.assertEqual(set(step["state"]["enum"]), literal(next(m for m in STEP_MODELS if "state" in m.model_fields).model_fields["state"].annotation))

    def test_targets_and_viewports(self) -> None:
        self.assertEqual(set(self.properties("record_walkthrough", "steps", "[]", "target")), fields(Target))
        self.assertEqual(set(self.properties("record_walkthrough", "steps", "[]", "to")), fields(Target))
        for action in ("inspect_page", "record_walkthrough", "render_scene"):
            self.assertEqual(set(self.properties(action, "viewport")), fields(Viewport), action)

    def test_scenes(self) -> None:
        self.assertEqual(set(self.properties("render_scene", "params")), fields(SceneParams))
        self.assertEqual(set(self.schemas["render_scene"]["properties"]["params"]["properties"]["theme"]["enum"]), literal(SceneParams.model_fields["theme"].annotation))
        self.assertEqual(set(self.schemas["render_scene"]["properties"]["template"]["enum"]), literal(SceneTemplateName))
        self.assertEqual(set(self.schemas["render_scene"]["properties"]["fps"]["enum"]), literal(FRAME_RATES))

    def test_compositions(self) -> None:
        self.check(Output, "compose_video", "output")
        self.check(Clip, "compose_video", "clips", "[]")
        self.check(ZoomKeyframe, "compose_video", "clips", "[]", "zoom", "[]")
        self.check(Transition, "compose_video", "clips", "[]", "transition_in")
        self.check(Overlay, "compose_video", "overlays", "[]")
        self.check(AudioBed, "compose_video", "audio")
        clip = self.properties("compose_video", "clips", "[]")
        self.assertEqual(set(clip["transition_in"]["properties"]["kind"]["enum"]), literal(TransitionKind))
        self.assertEqual(set(clip["fit"]["enum"]), literal(Clip.model_fields["fit"].annotation))
        self.assertEqual(set(clip["zoom"]["items"]["properties"]["ease"]["enum"]), literal(ZoomKeyframe.model_fields["ease"].annotation))
        self.assertEqual(set(self.properties("compose_video", "output")["fps"]["enum"]), literal(FRAME_RATES))


if __name__ == "__main__":
    unittest.main()
