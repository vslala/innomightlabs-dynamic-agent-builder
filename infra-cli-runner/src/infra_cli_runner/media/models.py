"""The editing timeline an agent sends to be turned into a video, and what comes back."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.infra_cli_runner.studio.models import MediaFile

#: ffmpeg's `xfade` transition names. A name that isn't listed here never reaches ffmpeg.
TransitionKind = Literal[
    "fade", "fadeblack", "dissolve", "wipeleft", "wiperight", "slideleft", "slideright", "smoothleft", "circleopen"
]
FRAME_RATES = Literal[24, 25, 30, 60]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ZoomKeyframe(_Model):
    """Eases the view to centre on (x, y) at `scale` times its size, starting `at` seconds into the clip."""

    at: float = Field(ge=0, le=3600)
    duration: float = Field(0.8, gt=0, le=10)
    x: float = Field(0.5, ge=0, le=1)
    y: float = Field(0.5, ge=0, le=1)
    scale: float = Field(1, ge=1, le=4)
    ease: Literal["linear", "ease_in_out"] = "ease_in_out"


class Transition(_Model):
    kind: TransitionKind = "fade"
    duration: float = Field(0.5, gt=0, le=3)


class Clip(_Model):
    source: str = Field(min_length=1, max_length=256)
    start: float = Field(0, ge=0)
    #: Seconds into the source. Omit for "to the end".
    end: float | None = Field(None, gt=0)
    speed: float = Field(1, ge=0.25, le=4)
    #: How long a still image is shown. Ignored for video.
    hold_seconds: float = Field(3, gt=0, le=30)
    fit: Literal["cover", "contain"] = "cover"
    background: str = Field("#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    zoom: list[ZoomKeyframe] = Field(default_factory=list, max_length=20)
    #: How this clip comes in from the one before. Omit for a hard cut. Ignored on the first clip.
    transition_in: Transition | None = None

    @field_validator("zoom")
    @classmethod
    def zoom_in_time_order(cls, keyframes: list[ZoomKeyframe]) -> list[ZoomKeyframe]:
        if [k.at for k in keyframes] != sorted(k.at for k in keyframes):
            raise ValueError("zoom keyframes must be in time order")
        return keyframes


class Overlay(_Model):
    """A transparent scene or image laid over the video from `at` for `duration` seconds."""

    source: str = Field(min_length=1, max_length=256)
    #: Which clip (by position, from 0) this overlay belongs to. `at` is then seconds after that clip begins in the
    #: finished video, so no one has to add up transitions. Omit to count `at` from the start of the video.
    clip: int | None = Field(None, ge=0)
    at: float = Field(0, ge=0)
    #: Omit to show the overlay for its own length (images: 3 seconds).
    duration: float | None = Field(None, gt=0)
    x: float = Field(0, ge=0, le=1)
    y: float = Field(0, ge=0, le=1)
    width: float = Field(1, gt=0, le=1)


class AudioBed(_Model):
    source: str = Field(min_length=1, max_length=256)
    volume: float = Field(0.8, ge=0, le=2)
    fade_in: float = Field(0, ge=0, le=10)
    fade_out: float = Field(1.5, ge=0, le=10)


class Output(_Model):
    path: str = Field(min_length=1, max_length=256)
    # Recordings are 1280x720 by default, so a larger output would only enlarge them.
    width: int = Field(1280, ge=320, le=1920)
    height: int = Field(720, ge=240, le=1080)
    fps: FRAME_RATES = 30

    @field_validator("width", "height")
    @classmethod
    def even(cls, value: int) -> int:
        if value % 2:
            raise ValueError("width and height must be even")
        return value


class CompositionRequest(_Model):
    request_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(pattern=r"^[a-f0-9]{48}$")
    output: Output
    clips: list[Clip] = Field(min_length=1, max_length=40)
    overlays: list[Overlay] = Field(default_factory=list, max_length=20)
    audio: AudioBed | None = None

    @model_validator(mode="after")
    def overlays_point_at_clips(self) -> "CompositionRequest":
        for overlay in self.overlays:
            if overlay.clip is not None and overlay.clip >= len(self.clips):
                raise ValueError(f"overlay {overlay.source} is for clip {overlay.clip}, but there are {len(self.clips)} clips")
        return self

    @model_validator(mode="after")
    def output_is_a_video_path(self) -> "CompositionRequest":
        if not self.output.path.lower().endswith((".mp4", ".webm")):
            raise ValueError("output.path must end in .mp4 or .webm")
        return self


class CompositionResponse(_Model):
    output: MediaFile
    #: What the timeline came to, in seconds, after transitions overlapped the clips.
    duration_seconds: float


class ProbeRequest(_Model):
    request_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(pattern=r"^[a-f0-9]{48}$")
    path: str = Field(min_length=1, max_length=256)
    #: Save one frame (a `.png` or `.jpg`) at this time, to look at.
    frame_at_seconds: float | None = Field(None, ge=0)
    frame_path: str | None = Field(None, max_length=256)
    #: Save one image of six evenly spaced frames (3 x 2), to check a whole video at a glance.
    sheet_path: str | None = Field(None, max_length=256)

    @model_validator(mode="after")
    def frame_needs_both(self) -> "ProbeRequest":
        if (self.frame_at_seconds is None) != (self.frame_path is None):
            raise ValueError("frame_at_seconds and frame_path go together")
        return self


class ProbeResponse(_Model):
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    has_audio: bool = False
    frame: str | None = None
    sheet: str | None = None


__all__ = [name for name in dir() if not name.startswith("_")]
