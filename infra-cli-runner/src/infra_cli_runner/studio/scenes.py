"""Renders an animated scene (a title card, an overlay, or the agent's own HTML) to a video, one frame at a time.

Rendering in real time would drop frames whenever the machine is busy, and motion graphics show every dropped frame.
So the clock is stopped, every CSS animation is paused and moved to the exact time of the frame, the frame is
captured, and only then does time move on: the same scene gives the same video however loaded the runner is.
"""

from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path

from playwright.async_api import Error as PlaywrightError

from src.infra_cli_runner.browser import SCENE_ORIGIN, BrowserRenderer, FetchedResource, RenderError
from src.infra_cli_runner.filesystem import FileSystemOperationError, FileSystemService
from src.infra_cli_runner.media import ffmpeg
from src.infra_cli_runner.studio.models import MediaFile, SceneRequest, SceneResponse
from src.infra_cli_runner.studio.templates import template_for

VIDEO_SUFFIXES = frozenset({".mp4", ".webm"})
TEMPLATE_PAGE = "__template__.html"
#: What a scene may load from the workspace. Anything else is a 404, whatever the workspace holds.
ASSET_SUFFIXES = frozenset(
    {".html", ".css", ".js", ".mjs", ".json", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".woff", ".woff2", ".ttf", ".otf"}
)
MAX_ASSET_BYTES = 25 * 1024 * 1024
SEEK_ANIMATIONS = "t => document.getAnimations().forEach(a => { a.pause(); a.currentTime = t; })"
SCENE_READY = "async () => { await document.fonts.ready; if (window.__studioReady) await window.__studioReady; }"
READY_TIMEOUT_SECONDS = 5
#: The fake clock stops here; anything a scene starts on load has begun by then.
CLOCK_START_MS = 1000
SECONDS_PER_FRAME_BUDGET = 0.25


def _scene_files(files: FileSystemService, workspace: Path, template_html: str | None):  # type: ignore[no-untyped-def]
    def read(path: str) -> FetchedResource | None:
        if template_html is not None and path == TEMPLATE_PAGE:
            return FetchedResource(200, {"content-type": "text/html; charset=utf-8"}, template_html.encode("utf-8"))
        try:
            file = files.resolve_existing(workspace, path, suffixes=ASSET_SUFFIXES)
            if file.stat().st_size > MAX_ASSET_BYTES:
                return None
            body = file.read_bytes()
        except (FileSystemOperationError, OSError):
            return None
        content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        return FetchedResource(200, {"content-type": content_type}, body)

    return read


def _encoder(request: SceneRequest, transparent: bool, target: Path) -> list[str]:
    frames_in = ["-f", "image2pipe", "-framerate", str(request.fps), "-c:v", "png" if transparent else "mjpeg", "-i", "-"]
    if target.suffix == ".mp4":
        video = ["-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-movflags", "+faststart"]
    elif transparent:
        video = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-crf", "30", "-b:v", "0", "-auto-alt-ref", "0"]
    else:
        video = ["-pix_fmt", "yuv420p", "-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0"]
    return [ffmpeg.ffmpeg_binary(), "-hide_banner", "-y", "-loglevel", "error", *frames_in, *video, "-r", str(request.fps), str(target)]


async def render_scene(renderer: BrowserRenderer, files: FileSystemService, request: SceneRequest) -> SceneResponse:
    workspace = files.workspace(request.workspace_id)
    suffix = Path(request.output_path).suffix.lower()
    template = template_for(request.template) if request.template else None
    transparent = template.transparent if template else request.transparent
    if transparent and suffix != ".webm":
        raise FileSystemOperationError("invalid_path", "a transparent scene keeps its alpha only as .webm")
    files.output_path(workspace, request.output_path, suffixes=VIDEO_SUFFIXES)
    if request.scene_path:
        files.resolve_existing(workspace, request.scene_path, suffixes=frozenset({".html"}))

    frames = round(request.duration_seconds * request.fps)
    html = template.html(request.params, request.duration_seconds) if template and request.params else None
    page_name = TEMPLATE_PAGE if template else request.scene_path or ""
    staged = files.staging_dir(workspace)
    pipe = None
    try:
        target = staged / f"scene{suffix}"
        pipe = ffmpeg.FramePipe(_encoder(request, transparent, target))
        deadline = frames * SECONDS_PER_FRAME_BUDGET + 40
        try:
            async with asyncio.timeout(deadline):
                await pipe.start()
                async with renderer.studio_page(
                    width=request.viewport.width,
                    height=request.viewport.height,
                    timeout_seconds=20,
                    scene_files=_scene_files(files, workspace, html),
                ) as page:
                    await _capture(page, pipe, page_name, frames, request.fps, transparent)
                finished = await pipe.finish(60)
        except TimeoutError as exc:
            raise RenderError("the scene took too long to render") from exc
        except PlaywrightError as exc:
            raise RenderError(f"couldn't render the scene: {str(exc).splitlines()[0]}") from exc
        if finished.returncode != 0 or not target.exists():
            raise ffmpeg.MediaError(f"ffmpeg couldn't encode the scene: {ffmpeg.tail(finished.stderr)}")
        size = target.stat().st_size
        path = files.commit_output(workspace, target, request.output_path, suffixes=VIDEO_SUFFIXES)
    finally:
        if pipe is not None:
            pipe.abort()
        files.release_staging(workspace, staged)
    output = MediaFile(
        path=path, size_bytes=size, duration_seconds=round(frames / request.fps, 2),
        width=request.viewport.width, height=request.viewport.height,
    )
    return SceneResponse(output=output, frames=frames)


async def _capture(page, pipe: ffmpeg.FramePipe, page_name: str, frames: int, fps: int, transparent: bool) -> None:  # type: ignore[no-untyped-def]
    await page.clock.install(time=0)
    try:
        await page.goto(f"{SCENE_ORIGIN}/{page_name}", wait_until="load")
    except PlaywrightError as exc:
        raise RenderError(f"couldn't load the scene: {str(exc).splitlines()[0]}") from exc
    try:
        await asyncio.wait_for(page.evaluate(SCENE_READY), READY_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        raise RenderError("the scene never became ready (window.__studioReady didn't resolve)") from exc
    await page.clock.pause_at(CLOCK_START_MS)
    frame_ms = 1000 / fps
    for index in range(frames):
        await page.evaluate(SEEK_ANIMATIONS, index * frame_ms)
        if transparent:
            image = await page.screenshot(type="png", omit_background=True)
        else:
            image = await page.screenshot(type="jpeg", quality=92)
        await pipe.write(image)
        # The clock takes whole milliseconds; stepping to each frame's rounded time keeps the total from drifting.
        await page.clock.run_for(round((index + 1) * frame_ms) - round(index * frame_ms))
