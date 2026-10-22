"""Joins workspace clips into a video and reads media back out: the endpoints' logic."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from src.infra_cli_runner.filesystem import FileSystemOperationError, FileSystemService
from src.infra_cli_runner.media import ffmpeg
from src.infra_cli_runner.media.compose import IMAGE_SUFFIXES, CompositionError, Source, build
from src.infra_cli_runner.media.models import CompositionRequest, CompositionResponse, ProbeRequest, ProbeResponse
from src.infra_cli_runner.studio.models import MediaFile

VIDEO_SUFFIXES = frozenset({".mp4", ".webm"})
FRAME_SUFFIXES = frozenset({".png", ".jpg", ".jpeg"})
READABLE_SUFFIXES = frozenset({".mp4", ".webm", ".mov", ".mkv", ".mp3", ".m4a", ".wav", ".ogg", *IMAGE_SUFFIXES})
SHEET_FRAMES = (3, 2)
SHEET_FRAME_WIDTH = 480
_slots: asyncio.Semaphore | None = None


def _compose_slot() -> asyncio.Semaphore:
    global _slots
    if _slots is None:
        _slots = asyncio.Semaphore(int(os.getenv("MEDIA_COMPOSE_CONCURRENCY", "1")))
    return _slots


def _timeout() -> float:
    return float(os.getenv("MEDIA_COMPOSE_TIMEOUT_SECONDS", "300"))


def _max_seconds() -> float:
    return float(os.getenv("MEDIA_COMPOSE_MAX_SECONDS", "300"))


async def compose(files: FileSystemService, request: CompositionRequest) -> CompositionResponse:
    workspace = files.workspace(request.workspace_id)
    out = request.output
    suffix = Path(out.path).suffix.lower()
    files.output_path(workspace, out.path, suffixes=VIDEO_SUFFIXES)

    names = {clip.source for clip in request.clips} | {o.source for o in request.overlays}
    if request.audio:
        names.add(request.audio.source)
    sources: dict[str, Source] = {}
    for name in sorted(names):
        path = files.resolve_existing(workspace, name, suffixes=READABLE_SUFFIXES)
        try:
            info = await ffmpeg.probe(path)
        except ffmpeg.MediaError as exc:
            raise CompositionError(f"{name}: {exc}") from exc
        sources[name] = Source(path, info.duration, info.has_audio)
    if request.audio and not sources[request.audio.source].has_audio:
        raise CompositionError(f"{request.audio.source} has no audio to use")

    built = build(request, sources, max_seconds=_max_seconds())
    staged = files.staging_dir(workspace)
    try:
        script = staged / "filters.txt"
        script.write_text(built.filter_graph, encoding="utf-8")
        target = staged / f"out{suffix}"
        argv = [
            ffmpeg.ffmpeg_binary(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
            *built.input_args, "-filter_complex_script", str(script), *built.map_args,
            *_encoding(suffix, out.fps, request.audio is not None), "-t", f"{built.duration:.3f}", str(target),
        ]
        async with _compose_slot():
            finished = await ffmpeg.run(argv, timeout_seconds=_timeout())
        if finished.returncode != 0 or not target.exists():
            raise ffmpeg.MediaError(f"ffmpeg couldn't build the video: {ffmpeg.tail(finished.stderr)}")
        size = target.stat().st_size
        path = files.commit_output(workspace, target, out.path, suffixes=VIDEO_SUFFIXES)
    finally:
        files.release_staging(workspace, staged)
    return CompositionResponse(
        output=MediaFile(path=path, size_bytes=size, duration_seconds=built.duration, width=out.width, height=out.height),
        duration_seconds=built.duration,
    )


def _encoding(suffix: str, fps: int, with_audio: bool) -> list[str]:
    if suffix == ".webm":
        video = ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-row-mt", "1"]
        audio = ["-c:a", "libopus", "-b:a", "128k"] if with_audio else []
        return [*video, *audio, "-r", str(fps)]
    video = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    audio = ["-c:a", "aac", "-b:a", "160k"] if with_audio else []
    return [*video, *audio, "-r", str(fps)]


async def probe_media(files: FileSystemService, request: ProbeRequest) -> ProbeResponse:
    workspace = files.workspace(request.workspace_id)
    path = files.resolve_existing(workspace, request.path, suffixes=READABLE_SUFFIXES)
    # Every output path is checked before any work is done.
    frame_target = files.output_path(workspace, request.frame_path, suffixes=FRAME_SUFFIXES) if request.frame_path else None
    sheet_target = files.output_path(workspace, request.sheet_path, suffixes=FRAME_SUFFIXES) if request.sheet_path else None
    info = await ffmpeg.probe(path)
    response = ProbeResponse(
        duration_seconds=round(info.duration, 2) if info.duration else None,
        width=info.width,
        height=info.height,
        fps=info.fps,
        has_audio=info.has_audio,
    )
    if frame_target is not None:
        response.frame = await _save_image(
            files, workspace, request.frame_path or "", ["-ss", f"{request.frame_at_seconds:.3f}", "-i", str(path), "-frames:v", "1"]
        )
    if sheet_target is not None:
        if not info.duration:
            raise ffmpeg.MediaError("can't make a contact sheet: the file has no length")
        columns, rows = SHEET_FRAMES
        frames = columns * rows
        # `fps` picks `frames` evenly spaced frames from the whole length; the last lands at the final instant.
        filters = f"fps={frames}/{info.duration:.3f},scale={SHEET_FRAME_WIDTH}:-2,tile={columns}x{rows}:padding=4:color=white"
        response.sheet = await _save_image(
            files, workspace, request.sheet_path or "", ["-i", str(path), "-vf", filters, "-frames:v", "1"]
        )
    return response


async def _save_image(files: FileSystemService, workspace: Path, raw: str, input_args: list[str]) -> str:
    staged = files.staging_dir(workspace)
    try:
        target = staged / f"image{Path(raw).suffix.lower()}"
        finished = await ffmpeg.run(
            [ffmpeg.ffmpeg_binary(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-protocol_whitelist", "file",
             *input_args, "-q:v", "3", str(target)],
            timeout_seconds=60,
        )
        if finished.returncode != 0 or not target.exists():
            raise ffmpeg.MediaError(f"couldn't save the image: {ffmpeg.tail(finished.stderr)}")
        return files.commit_output(workspace, target, raw, suffixes=FRAME_SUFFIXES)
    finally:
        files.release_staging(workspace, staged)


__all__ = ["compose", "probe_media", "CompositionError", "FileSystemOperationError"]
