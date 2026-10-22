"""Runs ffmpeg and ffprobe: fixed binaries, no shell, a sanitized environment and a deadline."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import signal
import tempfile
from dataclasses import dataclass
from pathlib import Path

STDERR_TAIL_BYTES = 2000
#: A recording from the browser is written live, so its header has no length; reading it means decoding it once.
DURATION_FROM_DECODE = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")


class MediaError(Exception):
    """ffmpeg or ffprobe failed; the message carries the end of its own explanation."""


def ffmpeg_binary() -> str:
    return os.getenv("FFMPEG_BIN") or shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_binary() -> str:
    return os.getenv("FFPROBE_BIN") or shutil.which("ffprobe") or "ffprobe"


def _environment() -> dict[str, str]:
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tempfile.gettempdir(), "LC_ALL": "C"}


@dataclass(frozen=True)
class Finished:
    returncode: int
    stdout: bytes
    stderr: str


async def run(argv: list[str], *, timeout_seconds: float, stdin: bytes | None = None) -> Finished:
    """Runs a command to completion, or kills its whole process group when the deadline passes."""
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_environment(),
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(stdin), timeout_seconds)
    except TimeoutError as exc:
        _kill(process)
        await process.wait()
        raise MediaError(f"ffmpeg took longer than {timeout_seconds:.0f}s and was stopped") from exc
    except asyncio.CancelledError:
        _kill(process)
        await process.wait()
        raise
    return Finished(process.returncode or 0, stdout, stderr.decode("utf-8", errors="replace"))


def _kill(process: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()


def tail(text: str) -> str:
    text = text.strip()
    return text if len(text) <= STDERR_TAIL_BYTES else "…" + text[-STDERR_TAIL_BYTES:]


@dataclass(frozen=True)
class MediaInfo:
    duration: float | None
    width: int | None
    height: int | None
    fps: float | None
    has_audio: bool


async def probe(path: Path, *, timeout_seconds: float = 60) -> MediaInfo:
    result = await run(
        [ffprobe_binary(), "-v", "error", "-protocol_whitelist", "file", "-show_entries",
         "format=duration:stream=codec_type,width,height,r_frame_rate", "-of", "json", str(path)],
        timeout_seconds=timeout_seconds,
    )
    if result.returncode != 0:
        raise MediaError(f"{path.name} isn't a readable media file: {tail(result.stderr)}")
    data = json.loads(result.stdout or b"{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    duration = _float(data.get("format", {}).get("duration"))
    if duration is None and video and path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        duration = await _duration_by_decoding(path, timeout_seconds)
    return MediaInfo(
        duration=duration,
        width=video.get("width"),
        height=video.get("height"),
        fps=_frame_rate(video.get("r_frame_rate")),
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
    )


async def _duration_by_decoding(path: Path, timeout_seconds: float) -> float | None:
    result = await run(
        [ffmpeg_binary(), "-hide_banner", "-nostdin", "-protocol_whitelist", "file", "-i", str(path), "-f", "null", "-"],
        timeout_seconds=timeout_seconds,
    )
    matches = DURATION_FROM_DECODE.findall(result.stderr)
    if not matches:
        return None
    hours, minutes, seconds = matches[-1]
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _frame_rate(value: object) -> float | None:
    try:
        numerator, denominator = str(value).split("/")
        return round(int(numerator) / int(denominator), 2) if int(denominator) else None
    except ValueError:
        return None


class FramePipe:
    """An ffmpeg process that is fed pictures one at a time and writes them out as a video."""

    def __init__(self, argv: list[str]) -> None:
        self._argv = argv
        self._process: asyncio.subprocess.Process | None = None
        self._stderr: asyncio.Task[bytes] | None = None

    async def start(self) -> None:
        self._process = await asyncio.create_subprocess_exec(
            *self._argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=_environment(),
            start_new_session=True,
        )
        # Read its complaints as they come, so a full pipe can never stall it.
        assert self._process.stderr is not None
        self._stderr = asyncio.create_task(self._process.stderr.read())

    async def write(self, image: bytes) -> None:
        assert self._process is not None and self._process.stdin is not None
        try:
            self._process.stdin.write(image)
            await self._process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise MediaError(f"ffmpeg stopped reading frames: {tail(await self._explanation())}") from exc

    async def finish(self, timeout_seconds: float) -> Finished:
        assert self._process is not None and self._process.stdin is not None
        self._process.stdin.close()
        try:
            await asyncio.wait_for(self._process.wait(), timeout_seconds)
        except TimeoutError as exc:
            self.abort()
            raise MediaError("ffmpeg didn't finish the video in time") from exc
        return Finished(self._process.returncode or 0, b"", await self._explanation())

    async def _explanation(self) -> str:
        return (await self._stderr).decode("utf-8", errors="replace") if self._stderr else ""

    def abort(self) -> None:
        if self._process is not None and self._process.returncode is None:
            _kill(self._process)
