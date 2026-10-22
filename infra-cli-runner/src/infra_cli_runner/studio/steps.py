"""Performs a list of typed steps in a page, in order, and says how long each took and where it stopped.

A step is data, never code: each kind is one strategy class, chosen by `strategy_for`. The same strategies run a
recorded walkthrough, a rehearsal of one, and the steps that bring a page to the state `inspect_page` should read.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from playwright.async_api import Error as PlaywrightError, Locator, Page, TimeoutError as PlaywrightTimeout

from src.infra_cli_runner.filesystem import FileSystemOperationError, FileSystemService
from src.infra_cli_runner.studio.models import (
    Box,
    ClickStep,
    GotoStep,
    HoverStep,
    MarkStep,
    Marker,
    PressStep,
    ScreenshotStep,
    ScrollStep,
    Step,
    StepErrorCode,
    StepTiming,
    Target,
    TypeStep,
    WaitForStep,
    WaitStep,
)
from src.infra_cli_runner.studio.targets import locate

SCREENSHOT_SUFFIXES = frozenset({".png", ".jpg", ".jpeg"})
#: A rehearsal exists to find what fails, so it doesn't sit through the pauses a viewer needs.
REHEARSAL_MAX_PAUSE_MS = 500
#: After an action, a beat for the result to show before the next thing happens.
BEAT_MS = 300
SCROLL_JS = """([top, duration]) => new Promise((resolve) => {
  const start = window.scrollY;
  const change = top - start;
  if (duration <= 0 || change === 0) { window.scrollTo({ top, behavior: 'instant' }); resolve(); return; }
  const began = performance.now();
  const frame = (now) => {
    const progress = Math.min(1, (now - began) / duration);
    window.scrollTo({ top: start + change * progress * progress * (3 - 2 * progress), behavior: 'instant' });
    if (progress < 1) requestAnimationFrame(frame); else resolve();
  };
  requestAnimationFrame(frame);
})"""
CENTER_OF_ELEMENT_JS = "el => { const r = el.getBoundingClientRect(); return r.top + window.scrollY + r.height / 2 - window.innerHeight / 2; }"


class StepError(Exception):
    """A step that couldn't be done. The code tells the agent what to change; the message says what happened."""

    def __init__(self, code: StepErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@contextmanager
def _acting() -> Iterator[None]:
    """Playwright waits for an element to be visible, enabled and unobscured; when it never is, that is this error."""
    try:
        yield
    except PlaywrightError as exc:
        raise StepError("not_actionable", _first_line(exc)) from exc


def _first_line(exc: Exception) -> str:
    return (str(exc).splitlines() or [exc.__class__.__name__])[0]


def check_step_paths(files: FileSystemService, workspace: Path, steps: list[Step]) -> None:
    """Fails before the browser starts if a screenshot path could never be written."""
    for step in steps:
        if isinstance(step, ScreenshotStep):
            files.output_path(workspace, step.path, suffixes=SCREENSHOT_SUFFIXES)


class StepRun:
    """What the strategies share: the page, the clock the markers are read from, and where the cursor is."""

    def __init__(
        self,
        page: Page,
        files: FileSystemService,
        workspace: Path,
        *,
        rehearse: bool,
        step_timeout_seconds: float,
    ) -> None:
        self.page = page
        self.files = files
        self.workspace = workspace
        self.rehearse = rehearse
        self.step_timeout_ms = step_timeout_seconds * 1000
        #: The browser starts recording when the page is created, which is when this clock starts.
        self.started = time.monotonic()
        self.markers: list[Marker] = []
        self.screenshots: list[str] = []
        self.mouse: tuple[float, float] | None = None
        self.last_box: Box | None = None

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    async def pause(self, ms: int) -> None:
        await asyncio.sleep((min(ms, REHEARSAL_MAX_PAUSE_MS) if self.rehearse else ms) / 1000)

    async def beat(self) -> None:
        if not self.rehearse:
            await self.pause(BEAT_MS)

    async def settle(self) -> None:
        """Gives a page that just changed a moment to finish loading; one that never goes idle is not waited out."""
        with suppress(PlaywrightTimeout):
            await self.page.wait_for_load_state("networkidle", timeout=1000 if self.rehearse else 3000)

    async def locate(self, target: Target) -> Locator:
        """The one element a target points at. A target that matches several is refused, never guessed at."""
        locator = locate(self.page, target)
        deadline = time.monotonic() + self.step_timeout_ms / 1000
        try:
            while (count := await locator.count()) == 0 and time.monotonic() < deadline:
                await asyncio.sleep(0.1)
        except PlaywrightError as exc:
            raise StepError("not_found", f"the target isn't usable: {_first_line(exc)}") from exc
        if count == 0:
            raise StepError("not_found", "no element on the page matches the target")
        if count > 1:
            raise StepError("ambiguous_target", f"{count} elements match the target; add nth to pick one")
        return locator

    async def approach(self, target: Target, move_ms: int) -> Locator:
        """Scrolls the target into view and, when recording, glides the cursor to it so a viewer can follow."""
        locator = await self.locate(target)
        with _acting():
            await locator.scroll_into_view_if_needed(timeout=self.step_timeout_ms)
            box = await locator.bounding_box(timeout=self.step_timeout_ms)
        if box is None:
            raise StepError("not_actionable", "the element has no box on the page")
        self._remember(box)
        if not self.rehearse:
            await self._glide(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, move_ms)
        return locator

    def _remember(self, box: dict[str, float]) -> None:
        size = self.page.viewport_size or {"width": 1, "height": 1}
        self.last_box = Box(
            x=round(max(0, box["x"]) / size["width"], 4),
            y=round(max(0, box["y"]) / size["height"], 4),
            width=round(box["width"] / size["width"], 4),
            height=round(box["height"] / size["height"], 4),
        )

    async def note_box(self, locator: Locator) -> None:
        """Records where a target ended up in the view, as a focus for a zoom."""
        box = await locator.bounding_box(timeout=self.step_timeout_ms)
        if box is not None:
            self._remember(box)

    async def _glide(self, x: float, y: float, move_ms: int) -> None:
        start_x, start_y = self.mouse or (x, y)
        steps = max(1, move_ms // 16)
        for step in range(1, steps + 1):
            progress = step / steps
            eased = progress * progress * (3 - 2 * progress)
            await self.page.mouse.move(start_x + (x - start_x) * eased, start_y + (y - start_y) * eased)
            await asyncio.sleep(move_ms / 1000 / steps)
        self.mouse = (x, y)

    async def redraw_cursor(self) -> None:
        """A new document starts without the cursor; moving the mouse to where it was draws it again."""
        if self.mouse is not None and not self.rehearse:
            await self.page.mouse.move(*self.mouse)


class StepStrategy(Protocol):
    action: str

    async def run(self, run: StepRun, step: Step) -> None: ...


class GotoStrategy:
    action = "goto"

    async def run(self, run: StepRun, step: GotoStep) -> None:  # type: ignore[override]
        try:
            await run.page.goto(step.url, wait_until="domcontentloaded", timeout=run.step_timeout_ms * 2)
        except PlaywrightError as exc:
            raise StepError("navigation_failed", _first_line(exc)) from exc
        await run.settle()
        await run.redraw_cursor()


class ClickStrategy:
    action = "click"

    async def run(self, run: StepRun, step: ClickStep) -> None:  # type: ignore[override]
        locator = await run.approach(step.target, step.move_ms)
        with _acting():
            await locator.click(timeout=run.step_timeout_ms)
        await run.beat()


class HoverStrategy:
    action = "hover"

    async def run(self, run: StepRun, step: HoverStep) -> None:  # type: ignore[override]
        locator = await run.approach(step.target, step.move_ms)
        with _acting():
            await locator.hover(timeout=run.step_timeout_ms)
        await run.beat()


class TypeStrategy:
    action = "type"

    async def run(self, run: StepRun, step: TypeStep) -> None:  # type: ignore[override]
        locator = await run.approach(step.target, 600)
        with _acting():
            await locator.click(timeout=run.step_timeout_ms)
            await locator.press_sequentially(step.text, delay=0 if run.rehearse else step.delay_ms, timeout=run.step_timeout_ms)
        await run.beat()


class PressStrategy:
    action = "press"

    async def run(self, run: StepRun, step: PressStep) -> None:  # type: ignore[override]
        with _acting():
            await run.page.keyboard.press(step.key)
        await run.beat()


class ScrollStrategy:
    action = "scroll"

    async def run(self, run: StepRun, step: ScrollStep) -> None:  # type: ignore[override]
        with _acting():
            if step.to is not None:
                locator = await run.locate(step.to)
                top = await locator.evaluate(CENTER_OF_ELEMENT_JS)
            else:
                top = await run.page.evaluate("window.scrollY") + (step.by_pixels or 0)
            await run.page.evaluate(SCROLL_JS, [max(0, top), 0 if run.rehearse else step.duration_ms])
            if step.to is not None:
                await run.note_box(locator)
        await run.beat()


class WaitStrategy:
    action = "wait"

    async def run(self, run: StepRun, step: WaitStep) -> None:  # type: ignore[override]
        await run.pause(step.ms)


class WaitForStrategy:
    action = "wait_for"

    async def run(self, run: StepRun, step: WaitForStep) -> None:  # type: ignore[override]
        locator = locate(run.page, step.target)
        locator = locator if step.target.nth is not None else locator.first
        try:
            await locator.wait_for(state=step.state, timeout=step.timeout_ms)
        except PlaywrightTimeout as exc:
            raise StepError("timeout", f"the target never became {step.state} within {step.timeout_ms} ms") from exc
        except PlaywrightError as exc:
            raise StepError("not_found", f"the target isn't usable: {_first_line(exc)}") from exc


class MarkStrategy:
    action = "mark"

    async def run(self, run: StepRun, step: MarkStep) -> None:  # type: ignore[override]
        run.markers.append(Marker(label=step.label, at_seconds=round(run.elapsed(), 2)))


class ScreenshotStrategy:
    action = "screenshot"

    async def run(self, run: StepRun, step: ScreenshotStep) -> None:  # type: ignore[override]
        image_type = "png" if step.path.lower().endswith(".png") else "jpeg"
        with _acting():
            image = await run.page.screenshot(type=image_type, full_page=step.full_page)
        try:
            run.screenshots.append(run.files.write_output(run.workspace, step.path, image, suffixes=SCREENSHOT_SUFFIXES))
        except FileSystemOperationError as exc:
            raise StepError("workspace_error", f"{exc.code}: {exc.message}") from exc


STEP_STRATEGIES: list[StepStrategy] = [
    GotoStrategy(),
    ClickStrategy(),
    HoverStrategy(),
    TypeStrategy(),
    PressStrategy(),
    ScrollStrategy(),
    WaitStrategy(),
    WaitForStrategy(),
    MarkStrategy(),
    ScreenshotStrategy(),
]


def strategy_for(step: Step) -> StepStrategy:
    return next(strategy for strategy in STEP_STRATEGIES if strategy.action == step.action)


@dataclass
class FailedStep:
    index: int
    error: StepError


@dataclass
class StepsOutcome:
    timings: list[StepTiming] = field(default_factory=list)
    failed: FailedStep | None = None


async def run_steps(run: StepRun, steps: list[Step], *, deadline: float | None = None) -> StepsOutcome:
    """Runs the steps in order and stops at the first that fails; the rest are reported as skipped.

    `deadline` is a `time.monotonic()` time. A step still running when it passes fails with `timeout`."""
    outcome = StepsOutcome()
    for index, step in enumerate(steps):
        started = run.elapsed()
        if outcome.failed is not None:
            outcome.timings.append(_timing(index, step, "skipped", started, started))
            continue
        run.last_box = None
        try:
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                raise StepError("timeout", "the recording's time limit was reached before this step")
            async with asyncio.timeout(remaining):
                await strategy_for(step).run(run, step)
        except StepError as exc:
            outcome.failed = FailedStep(index, exc)
        except TimeoutError:
            outcome.failed = FailedStep(index, StepError("timeout", "the recording's time limit was reached during this step"))
        except PlaywrightError as exc:
            outcome.failed = FailedStep(index, StepError("not_actionable", _first_line(exc)))
        failure = outcome.failed.error if outcome.failed and outcome.failed.index == index else None
        outcome.timings.append(
            _timing(index, step, "failed" if failure else "ok", started, run.elapsed(), failure.message if failure else None, run.last_box)
        )
    return outcome


def _timing(index: int, step: Step, status: str, started: float, ended: float, error: str | None = None, box: Box | None = None) -> StepTiming:
    return StepTiming(
        index=index,
        action=step.action,
        status=status,  # type: ignore[arg-type]
        started_at_seconds=round(started, 2),
        ended_at_seconds=round(ended, 2),
        error=error,
        box=box,
    )


async def add_cursor(page: Page) -> None:
    """Draws a visible cursor on every page of this recording."""
    await page.add_init_script(path=Path(__file__).with_name("cursor.js"))


async def add_keepalive(page: Page) -> None:
    """Keeps a still page repainting, so the browser's recorder keeps getting frames (see `keepalive.js`)."""
    await page.add_init_script(path=Path(__file__).with_name("keepalive.js"))
