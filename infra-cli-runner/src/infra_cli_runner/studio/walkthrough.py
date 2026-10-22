"""Performs a list of steps in a browser and, unless it is only a rehearsal, records the screen as a video.

The agent writes the steps from what `inspect_page` showed it. A rehearsal runs them without recording or pacing, to
find the ones that fail; when one does, the answer carries the page as it was and the elements the step most likely
meant, so the agent corrects it from data rather than guessing again.
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path

from playwright.async_api import Error as PlaywrightError

from src.infra_cli_runner.browser import BrowserRenderer, RenderError
from src.infra_cli_runner.filesystem import FileSystemService
from src.infra_cli_runner.media import ffmpeg
from src.infra_cli_runner.studio.inspect import read_page
from src.infra_cli_runner.studio.models import (
    ClickStep,
    HoverStep,
    MediaFile,
    Marker,
    PageElement,
    ScrollStep,
    Step,
    StepFailure,
    Target,
    TypeStep,
    WaitForStep,
    WalkthroughRequest,
    WalkthroughResponse,
)
from src.infra_cli_runner.studio.steps import (
    FailedStep,
    StepRun,
    add_cursor,
    add_keepalive,
    check_step_paths,
    run_steps,
)

VIDEO_SUFFIXES = frozenset({".webm"})
#: Setup before the steps and finishing the video after them, on top of the recording's own limit.
OVERHEAD_SECONDS = 30
MAX_CANDIDATES = 10
FAILURE_PAGE_ELEMENTS = 40


async def walkthrough(renderer: BrowserRenderer, files: FileSystemService, request: WalkthroughRequest) -> WalkthroughResponse:
    workspace = files.workspace(request.workspace_id)
    # Every path is checked before the browser starts, so a typo doesn't cost a recording.
    check_step_paths(files, workspace, request.steps)
    if not request.rehearse:
        files.output_path(workspace, request.output_path or "", suffixes=VIDEO_SUFFIXES)
    staged = None if request.rehearse else files.staging_dir(workspace)
    try:
        async with asyncio.timeout(request.max_duration_seconds + OVERHEAD_SECONDS):
            async with renderer.studio_page(
                width=request.viewport.width,
                height=request.viewport.height,
                timeout_seconds=request.step_timeout_seconds,
                record_video_dir=staged,
            ) as page:
                result = await _perform(page, files, workspace, request)
            duration = result.duration
            if staged is not None:
                result.response.output = await _saved_video(page, files, workspace, staged, request, duration)
            return result.response
    except TimeoutError as exc:
        raise RenderError("the browser took too long") from exc
    except PlaywrightError as exc:
        raise RenderError(f"couldn't read the page: {str(exc).splitlines()[0]}") from exc
    finally:
        if staged is not None:
            files.release_staging(workspace, staged)


class _Performed:
    def __init__(self, response: WalkthroughResponse, duration: float) -> None:
        self.response = response
        self.duration = duration


async def _perform(page, files: FileSystemService, workspace: Path, request: WalkthroughRequest) -> _Performed:  # type: ignore[no-untyped-def]
    run = StepRun(page, files, workspace, rehearse=request.rehearse, step_timeout_seconds=request.step_timeout_seconds)
    deadline = time.monotonic() + request.max_duration_seconds
    if not request.rehearse:
        await add_keepalive(page)
        if request.show_cursor:
            await add_cursor(page)
    try:
        await page.goto(request.url, wait_until="domcontentloaded", timeout=request.step_timeout_seconds * 2000)
    except PlaywrightError as exc:
        raise RenderError(f"couldn't load the page: {str(exc).splitlines()[0]}") from exc
    await run.settle()
    # When the page was ready: where an agent should start a clip, without guessing from its own marks.
    run.markers.append(Marker(label="ready", at_seconds=round(run.elapsed(), 2)))

    outcome = await run_steps(run, request.steps, deadline=deadline)
    failure = await _failure(page, request.steps, outcome.failed) if outcome.failed else None
    duration = run.elapsed()
    response = WalkthroughResponse(
        status="partial" if failure else "success",
        markers=run.markers,
        steps=outcome.timings,
        screenshots=run.screenshots,
        final_url=page.url,
        failure=failure,
    )
    return _Performed(response, duration)


async def _saved_video(
    page, files: FileSystemService, workspace: Path, staged: Path, request: WalkthroughRequest, duration: float  # type: ignore[no-untyped-def]
) -> MediaFile:
    # The browser writes the file when its context closes, which has happened by now.
    recorded = await _trimmed(Path(await page.video.path()), staged, duration)
    size = recorded.stat().st_size
    path = files.commit_output(workspace, recorded, request.output_path or "", suffixes=VIDEO_SUFFIXES)
    return MediaFile(
        path=path,
        size_bytes=size,
        duration_seconds=round(duration, 2),
        width=request.viewport.width,
        height=request.viewport.height,
    )


async def _trimmed(recorded: Path, staged: Path, seconds: float) -> Path:
    """The browser keeps filming for a second or so after the last step, through its own shutdown. Cutting the tail (a
    stream copy, so nothing is re-encoded) makes the file end where the steps did, so `duration_seconds` and the file
    agree. The browser's encoder can still be finishing its last writes when the context has closed, so the cut waits
    for the file to stop growing, and a cut that comes out short is thrown away: the original is always the fallback."""
    await _stopped_growing(recorded)
    target = staged / "trimmed.webm"
    try:
        finished = await ffmpeg.run(
            [ffmpeg.ffmpeg_binary(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-protocol_whitelist", "file",
             "-i", str(recorded), "-c", "copy", "-t", f"{seconds + 0.05:.2f}", str(target)],
            timeout_seconds=60,
        )
        if finished.returncode != 0 or not target.exists():
            return recorded
        length = (await ffmpeg.probe(target)).duration
    except (OSError, ffmpeg.MediaError):
        return recorded
    return target if length is not None and length >= seconds - 0.3 else recorded


async def _stopped_growing(path: Path, *, settle_seconds: float = 0.3, limit_seconds: float = 10) -> None:
    deadline = time.monotonic() + limit_seconds
    previous = -1
    while time.monotonic() < deadline:
        size = path.stat().st_size
        if size == previous:
            return
        previous = size
        await asyncio.sleep(settle_seconds)


async def _failure(page, steps: list[Step], failed: FailedStep) -> StepFailure:  # type: ignore[no-untyped-def]
    try:
        reading = await read_page(page, max_elements=FAILURE_PAGE_ELEMENTS, outline_bytes=0)
    except PlaywrightError:
        # The page may have navigated away or closed under the step; the code and message still say what went wrong.
        return StepFailure(index=failed.index, error_code=failed.error.code, message=failed.error.message)
    snapshot = reading.snapshot
    candidates = _candidates(snapshot.elements, _target_of(steps[failed.index]))
    return StepFailure(
        index=failed.index, error_code=failed.error.code, message=failed.error.message, candidates=candidates, page=snapshot
    )


def _target_of(step: Step) -> Target | None:
    if isinstance(step, (ClickStep, HoverStep, TypeStep, WaitForStep)):
        return step.target
    return step.to if isinstance(step, ScrollStep) else None


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _candidates(elements: list[PageElement], target: Target | None) -> list[PageElement]:
    """What the step probably meant: elements whose name shares words with the target, then others of the same role."""
    if target is None:
        return []
    wanted = _words(target.name or target.text or "")
    related = [
        element for element in elements if (wanted & _words(element.name)) or (target.role is not None and element.role == target.role)
    ]
    related.sort(key=lambda element: -len(wanted & _words(element.name)))
    return related[:MAX_CANDIDATES]
