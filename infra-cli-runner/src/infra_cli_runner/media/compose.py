"""Turns a composition request into an ffmpeg filter graph. Pure: it runs nothing, so every shape of timeline can be
checked without ffmpeg, and no caller-supplied text ever reaches ffmpeg except as a number or a name from an allowlist.

Each clip is cut, sped up, fitted to the frame and zoomed on its own; the clips are then joined in order, with a
cross-fade where one asks for it and a hard cut where it doesn't. Overlays go on top, and audio is trimmed to fit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.infra_cli_runner.media.models import AudioBed, Clip, CompositionRequest, Overlay, ZoomKeyframe

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
DEFAULT_OVERLAY_IMAGE_SECONDS = 3


class CompositionError(ValueError):
    """The timeline can't be made into a video; the message says which part and why."""


@dataclass(frozen=True)
class Source:
    path: Path
    duration: float | None
    has_audio: bool = False

    @property
    def is_image(self) -> bool:
        return self.path.suffix.lower() in IMAGE_SUFFIXES


@dataclass(frozen=True)
class Built:
    input_args: list[str]
    filter_graph: str
    map_args: list[str]
    duration: float


def build(request: CompositionRequest, sources: dict[str, Source], *, max_seconds: float) -> Built:
    out = request.output
    input_args: list[str] = []
    graph: list[str] = []
    durations: list[float] = []

    for index, clip in enumerate(request.clips):
        source = sources[clip.source]
        duration, trim = _clip_span(index, clip, source)
        durations.append(duration)
        input_args += _clip_input(clip, source)
        graph.append(_clip_chain(index, clip, trim, out.width, out.height, out.fps))

    label, total, starts = _join(request.clips, durations, graph, out.fps)
    if total > max_seconds:
        raise CompositionError(f"the timeline is {total:.0f}s long; the limit is {max_seconds:.0f}s")

    next_input = len(request.clips)
    for position, overlay in enumerate(request.overlays):
        source = sources[overlay.source]
        input_args += _overlay_input(overlay, source)
        begins = (starts[overlay.clip] if overlay.clip is not None else 0) + overlay.at
        label = _add_overlay(graph, label, next_input + position, overlay, source, begins, out.width, out.height, out.fps)
    next_input += len(request.overlays)

    graph.append(f"[{label}]format=yuv420p[vout]")
    map_args = ["-map", "[vout]"]
    if request.audio is not None:
        source = sources[request.audio.source]
        input_args += ["-i", str(source.path)]
        graph.append(_audio_chain(next_input, request.audio, total))
        map_args += ["-map", "[aout]"]
    return Built(input_args, ";\n".join(graph), map_args, round(total, 3))


def _num(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".") or "0"


def _clip_span(index: int, clip: Clip, source: Source) -> tuple[float, tuple[float, float] | None]:
    """How long the clip plays once cut and sped up, and the (start, end) cut, none for a still image."""
    if source.is_image:
        return clip.hold_seconds, None
    available = source.duration or 0
    end = min(clip.end, available) if clip.end is not None else available
    if clip.start >= end:
        raise CompositionError(f"clip {index} ({clip.source}): start {clip.start}s is not before its end {end:.2f}s")
    return (end - clip.start) / clip.speed, (clip.start, end)


def _clip_input(clip: Clip, source: Source) -> list[str]:
    guard = ["-protocol_whitelist", "file,pipe"]
    if source.is_image:
        return [*guard, "-loop", "1", "-framerate", "30", "-t", _num(clip.hold_seconds), "-i", str(source.path)]
    return [*guard, "-i", str(source.path)]


def _clip_chain(index: int, clip: Clip, trim: tuple[float, float] | None, width: int, height: int, fps: int) -> str:
    steps = [f"trim=start={_num(trim[0])}:end={_num(trim[1])}"] if trim else []
    steps += [f"setpts=(PTS-STARTPTS)/{_num(clip.speed)}", f"fps={fps}"]
    if clip.fit == "cover":
        steps += [f"scale={width}:{height}:force_original_aspect_ratio=increase", f"crop={width}:{height}"]
    else:
        steps += [
            f"scale={width}:{height}:force_original_aspect_ratio=decrease",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={clip.background.replace('#', '0x')}",
        ]
    if clip.zoom:
        steps += _zoom(clip.zoom, clip.speed, width, height)
    # xfade and concat need every stream on the same frame rate and timebase; `fps` last makes it 1/fps.
    steps += ["setsar=1", "format=yuv420p", f"fps={fps}"]
    return f"[{index}:v]" + ",".join(steps) + f"[v{index}]"


def _zoom(keyframes: list[ZoomKeyframe], speed: float, width: int, height: int) -> list[str]:
    """Scale up by a time-varying factor, then crop back to the frame around a time-varying centre. Each keyframe adds
    the change it makes, eased in over its duration, so keyframes in sequence compose into one smooth move."""

    def progress(keyframe: ZoomKeyframe) -> str:
        span = max(keyframe.duration / speed, 0.01)
        ramp = f"clip((t-{_num(keyframe.at / speed)})/{_num(span)},0,1)"
        return ramp if keyframe.ease == "linear" else f"({ramp}*{ramp}*(3-2*{ramp}))"

    def track(values: list[float], start: float) -> str:
        expression, previous = _num(start), start
        for keyframe, value in zip(keyframes, values):
            expression += f"+({_num(value - previous)})*{progress(keyframe)}"
            previous = value
        return f"({expression})"

    factor = track([k.scale for k in keyframes], 1.0)
    centre_x = track([k.x for k in keyframes], 0.5)
    centre_y = track([k.y for k in keyframes], 0.5)
    return [
        f"scale=w='trunc({width}*{factor}/2)*2':h='trunc({height}*{factor}/2)*2':eval=frame",
        f"crop={width}:{height}:x='clip({centre_x}*iw-{width}/2,0,iw-{width})':y='clip({centre_y}*ih-{height}/2,0,ih-{height})'",
    ]


def _join(clips: list[Clip], durations: list[float], graph: list[str], fps: int) -> tuple[str, float, list[float]]:
    """Joins the clips in order. Returns the last stream, the total length and when each clip begins in the result."""
    label, length, starts = "v0", durations[0], [0.0]
    for index in range(1, len(clips)):
        joined = f"j{index}"
        transition = clips[index].transition_in
        if transition is None:
            graph.append(f"[{label}][v{index}]concat=n=2:v=1:a=0,fps={fps}[{joined}]")
            starts.append(length)
            length += durations[index]
        else:
            overlap = min(transition.duration, durations[index], length) * 0.99
            graph.append(
                f"[{label}][v{index}]xfade=transition={transition.kind}:duration={_num(overlap)}:offset={_num(length - overlap)},"
                f"fps={fps}[{joined}]"
            )
            starts.append(length - overlap)
            length += durations[index] - overlap
        label = joined
    return label, length, starts


def _overlay_input(overlay: Overlay, source: Source) -> list[str]:
    guard = ["-protocol_whitelist", "file,pipe"]
    if source.is_image:
        seconds = overlay.duration or DEFAULT_OVERLAY_IMAGE_SECONDS
        return [*guard, "-loop", "1", "-framerate", "30", "-t", _num(seconds), "-i", str(source.path)]
    # The browser's alpha channel is only kept by the libvpx decoder, which must be named before the input.
    codec = ["-c:v", "libvpx-vp9"] if source.path.suffix.lower() == ".webm" else []
    return [*guard, *codec, "-i", str(source.path)]


def _add_overlay(
    graph: list[str], base: str, input_index: int, overlay: Overlay, source: Source, begins: float, width: int, height: int, fps: int
) -> str:
    length = overlay.duration or source.duration or DEFAULT_OVERLAY_IMAGE_SECONDS
    shown = f"o{input_index}"
    graph.append(
        f"[{input_index}:v]format=yuva420p,fps={fps},setpts=PTS-STARTPTS+{_num(begins)}/TB,"
        f"scale={round(width * overlay.width / 2) * 2}:-2[{shown}]"
    )
    result = f"m{input_index}"
    graph.append(
        f"[{base}][{shown}]overlay=x={round(overlay.x * width)}:y={round(overlay.y * height)}:"
        f"enable='between(t,{_num(begins)},{_num(begins + length)})':eof_action=pass:format=auto[{result}]"
    )
    return result


def _audio_chain(input_index: int, audio: AudioBed, total: float) -> str:
    steps = [f"atrim=0:{_num(total)}", "asetpts=PTS-STARTPTS"]
    if audio.fade_in:
        steps.append(f"afade=t=in:d={_num(audio.fade_in)}")
    if audio.fade_out:
        steps.append(f"afade=t=out:st={_num(max(0, total - audio.fade_out))}:d={_num(audio.fade_out)}")
    steps.append(f"volume={_num(audio.volume)}")
    return f"[{input_index}:a]" + ",".join(steps) + "[aout]"
