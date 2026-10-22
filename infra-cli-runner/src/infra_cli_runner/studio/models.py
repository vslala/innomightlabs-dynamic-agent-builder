"""Request and response models for the browser studio endpoints."""

from __future__ import annotations

import os
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer, model_validator

DEFAULT_INSPECT_TIMEOUT_SECONDS = 25
KEY_PATTERN = (
    r"^(?:(?:Shift|Control|Alt|Meta)\+)*"
    r"(?:[A-Za-z0-9]|Enter|Tab|Escape|Backspace|Space|Arrow(?:Up|Down|Left|Right)|PageUp|PageDown|Home|End)$"
)


def validate_http_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("url must be an http or https address")
    return value


class Viewport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int = Field(1280, ge=320, le=1920)
    height: int = Field(720, ge=240, le=1080)


class Target(BaseModel):
    """Exactly one way to find an element. `nth` picks among several matches, in the order Playwright finds them."""

    model_config = ConfigDict(extra="forbid")

    selector: str | None = Field(None, max_length=512)
    role: str | None = Field(None, pattern=r"^[a-z]+$", max_length=32)
    name: str | None = Field(None, max_length=200)
    text: str | None = Field(None, max_length=200)
    nth: int | None = Field(None, ge=0, le=50)

    @model_validator(mode="after")
    def exactly_one_way_to_find_it(self) -> "Target":
        ways = [self.selector is not None, self.role is not None, self.text is not None]
        if sum(ways) != 1:
            raise ValueError("a target needs exactly one of selector, role or text")
        if self.name is not None and self.role is None:
            raise ValueError("name only goes with role")
        return self


class Box(BaseModel):
    """A rectangle as fractions of the whole page (an inventory) or of the viewport (where a step acted)."""

    x: float
    y: float
    width: float
    height: float


class _Step(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GotoStep(_Step):
    action: Literal["goto"]
    url: str = Field(min_length=1, max_length=2048)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return validate_http_url(value)


class ClickStep(_Step):
    action: Literal["click"]
    target: Target
    move_ms: int = Field(600, ge=0, le=3000)


class HoverStep(_Step):
    action: Literal["hover"]
    target: Target
    move_ms: int = Field(600, ge=0, le=3000)


class TypeStep(_Step):
    action: Literal["type"]
    target: Target
    text: str = Field(max_length=500)
    delay_ms: int = Field(60, ge=0, le=300)


class PressStep(_Step):
    action: Literal["press"]
    key: str = Field(pattern=KEY_PATTERN)


class ScrollStep(_Step):
    action: Literal["scroll"]
    to: Target | None = None
    by_pixels: int | None = Field(None, ge=-20000, le=20000)
    duration_ms: int = Field(1200, ge=0, le=10000)

    @model_validator(mode="after")
    def one_destination(self) -> "ScrollStep":
        if (self.to is None) == (self.by_pixels is None):
            raise ValueError("scroll needs exactly one of to or by_pixels")
        return self


class WaitStep(_Step):
    action: Literal["wait"]
    ms: int = Field(ge=0, le=15000)


class WaitForStep(_Step):
    action: Literal["wait_for"]
    target: Target
    state: Literal["visible", "hidden"] = "visible"
    timeout_ms: int = Field(10000, ge=100, le=30000)


class MarkStep(_Step):
    action: Literal["mark"]
    label: str = Field(pattern=r"^[a-z0-9_-]{1,40}$")


class ScreenshotStep(_Step):
    action: Literal["screenshot"]
    path: str = Field(min_length=1, max_length=256)
    full_page: bool = False


Step = Annotated[
    GotoStep | ClickStep | HoverStep | TypeStep | PressStep | ScrollStep | WaitStep | WaitForStep | MarkStep | ScreenshotStep,
    Field(discriminator="action"),
]


class StepTiming(BaseModel):
    index: int
    action: str
    status: Literal["ok", "failed", "skipped"]
    started_at_seconds: float
    ended_at_seconds: float
    error: str | None = None
    #: Where the step's target was in the viewport when it acted: a ready focus point for a zoom.
    box: Box | None = None


class PageElement(BaseModel):
    id: str
    role: str
    name: str
    target: Target
    #: Where the element sits down the page, 0 (top) to 1 (bottom).
    y: float
    #: Kept for sorting and for drawing the annotated screenshot, but never sent: an agent that wants a zoom focus gets it
    #: from the box a rehearsed step reports, and the rest costs tokens.
    box: Box = Field(exclude=True)
    in_first_viewport: bool = Field(exclude=True)
    section: str | None = None
    state: list[str] | None = None

    @model_serializer(mode="wrap")
    def drop_repeated_name(self, handler):  # type: ignore[no-untyped-def]
        data = handler(self)
        if data.get("name") == (data.get("target") or {}).get("name"):
            del data["name"]  # the target already says it
        return data


class Section(BaseModel):
    heading: str
    level: int
    target: Target
    top: float

    @model_serializer(mode="wrap")
    def drop_repeated_heading(self, handler):  # type: ignore[no-untyped-def]
        data = handler(self)
        if data.get("heading") == (data.get("target") or {}).get("name"):
            del data["heading"]
        return data


class InspectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(pattern=r"^[a-f0-9]{48}$")
    url: str = Field(min_length=1, max_length=2048)
    #: Reach a state first (open a menu, go to a tab). Run like a rehearsal: no cursor, short waits.
    steps: list[Step] = Field(default_factory=list, max_length=30)
    viewport: Viewport = Field(default_factory=Viewport)
    scroll_through: bool = True
    roles: list[str] = Field(default_factory=list, max_length=20)
    query: str | None = Field(None, max_length=100)
    max_elements: int = Field(80, ge=1, le=200)
    #: Sections are headings down to this level. Card titles are usually h3 and several times the size of the rest.
    max_heading_level: int = Field(2, ge=1, le=3)
    screenshot_path: str | None = Field(None, max_length=256)
    annotate: bool = False
    #: The accessibility outline is about half of a page's response and the sections already give its shape, so it is
    #: opt-in. Ask for it when the section list isn't enough.
    include_outline: bool = False
    timeout_seconds: int = Field(DEFAULT_INSPECT_TIMEOUT_SECONDS, validate_default=True)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return validate_http_url(value)

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: int) -> int:
        return max(1, min(value, int(os.getenv("BROWSER_STUDIO_MAX_INSPECT_SECONDS", "60"))))


class PageSnapshot(BaseModel):
    """What a page holds at one moment: the overview, what can be acted on, and where its sections start."""

    final_url: str
    title: str
    page_height_px: int
    outline: str | None = None
    elements: list[PageElement]
    sections: list[Section]
    truncated: bool


class InspectResponse(PageSnapshot):
    screenshot: str
    steps: list[StepTiming] = Field(default_factory=list)


class Marker(BaseModel):
    label: str
    at_seconds: float


class MediaFile(BaseModel):
    path: str
    size_bytes: int
    #: Measured from the browser's clock, not probed from the file: good to roughly a tenth of a second.
    duration_seconds: float
    width: int
    height: int


StepErrorCode = Literal["not_found", "ambiguous_target", "not_actionable", "timeout", "navigation_failed", "workspace_error"]


class StepFailure(BaseModel):
    index: int
    error_code: StepErrorCode
    message: str
    #: Up to 10 elements on the page that look like what the step was after: same role, or a name sharing words with it.
    candidates: list[PageElement] = Field(default_factory=list)
    #: The page as it was when the step failed; absent if the page could no longer be read.
    page: PageSnapshot | None = None


class WalkthroughRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(pattern=r"^[a-f0-9]{48}$")
    url: str = Field(min_length=1, max_length=2048)
    steps: list[Step] = Field(default_factory=list, max_length=100)
    #: Where the `.webm` goes. Required when recording; a rehearsal records nothing and ignores it.
    output_path: str | None = Field(None, max_length=256)
    viewport: Viewport = Field(default_factory=Viewport)
    show_cursor: bool = True
    #: Run the steps with no video, no cursor glide and waits capped at 500 ms, to find what fails cheaply.
    rehearse: bool = False
    # validate_default: the cap applies to the default too, which Pydantic otherwise skips.
    max_duration_seconds: int = Field(120, ge=1, validate_default=True)
    step_timeout_seconds: int = Field(10, ge=1, le=30)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return validate_http_url(value)

    @field_validator("max_duration_seconds")
    @classmethod
    def validate_duration(cls, value: int) -> int:
        return min(value, int(os.getenv("BROWSER_STUDIO_MAX_RECORD_SECONDS", "180")))

    @model_validator(mode="after")
    def recording_needs_a_webm_path(self) -> "WalkthroughRequest":
        if not self.rehearse and not (self.output_path or "").lower().endswith(".webm"):
            raise ValueError("output_path must be a .webm path when recording")
        labels = [step.label for step in self.steps if isinstance(step, MarkStep)]
        if len(labels) != len(set(labels)):
            raise ValueError("mark labels must be unique")
        if "ready" in labels:
            raise ValueError("the mark label 'ready' is the runner's own: it says when the page was ready")
        return self


class WalkthroughResponse(BaseModel):
    #: `partial`: a step failed or time ran out. A recording is still saved up to that point.
    status: Literal["success", "partial"]
    output: MediaFile | None = None
    markers: list[Marker] = Field(default_factory=list)
    steps: list[StepTiming] = Field(default_factory=list)
    screenshots: list[str] = Field(default_factory=list)
    final_url: str
    failure: StepFailure | None = None


SceneTemplateName = Literal["title", "outro", "lower_third"]


class SceneParams(BaseModel):
    """What a built-in scene says and how it looks."""

    model_config = ConfigDict(extra="forbid")

    heading: str = Field(min_length=1, max_length=120)
    subheading: str | None = Field(None, max_length=200)
    #: A small label above the heading (title only).
    eyebrow: str | None = Field(None, max_length=40)
    #: A call to action such as a web address (outro only).
    footer: str | None = Field(None, max_length=80)
    accent: str = Field("#6366f1", pattern=r"^#[0-9a-fA-F]{6}$")
    theme: Literal["dark", "light"] = "dark"


class SceneRequest(BaseModel):
    """Renders an animated scene to a video file, frame by frame, from a template or from the agent's own HTML."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(pattern=r"^[a-f0-9]{48}$")
    template: SceneTemplateName | None = None
    params: SceneParams | None = None
    #: Your own scene: a `.html` file in the workspace. Its relative assets (images, CSS, fonts) load from the workspace.
    scene_path: str | None = Field(None, max_length=256)
    output_path: str = Field(min_length=1, max_length=256)
    duration_seconds: float = Field(gt=0.2, le=30)
    fps: Literal[24, 25, 30, 60] = 30
    viewport: Viewport = Field(default_factory=lambda: Viewport(width=1280, height=720))
    #: Keep the page's transparency (a `.webm`), to lay over footage. Templates decide this themselves.
    transparent: bool = False

    @model_validator(mode="after")
    def one_source(self) -> "SceneRequest":
        if (self.template is None) == (self.scene_path is None):
            raise ValueError("give exactly one of template or scene_path")
        if self.template is not None and self.params is None:
            raise ValueError("a template needs params")
        if self.template is None and self.params is not None:
            raise ValueError("params go with a template")
        if self.scene_path is not None and not self.scene_path.lower().endswith(".html"):
            raise ValueError("scene_path must be a .html file")
        if not self.output_path.lower().endswith((".mp4", ".webm")):
            raise ValueError("output_path must end in .mp4 or .webm")
        return self


class SceneResponse(BaseModel):
    output: MediaFile
    frames: int
