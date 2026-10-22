from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError

from main import app
from src.infra_cli_runner.filesystem import FileSystemOperationError, FileSystemService
from src.infra_cli_runner.media import ffmpeg
from src.infra_cli_runner.media.compose import CompositionError, Source, build
from src.infra_cli_runner.media.models import CompositionRequest, CompositionResponse, ProbeRequest
from src.infra_cli_runner.media.service import compose, probe_media

WORKSPACE_ID = "d" * 48
HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def request(**fields: object) -> CompositionRequest:
    base = {"request_id": "r", "workspace_id": WORKSPACE_ID, "output": {"path": "out/v.mp4"}, "clips": [{"source": "a.mp4"}, {"source": "b.mp4"}]}
    return CompositionRequest(**{**base, **fields})  # type: ignore[arg-type]


def sources(**durations: float) -> dict[str, Source]:
    return {f"{name}.mp4": Source(Path(f"/ws/{name}.mp4"), seconds) for name, seconds in durations.items()}


class BuilderTests(unittest.TestCase):
    """The filter graph is pure text, so what it says can be checked without running ffmpeg."""

    def test_a_cross_fade_overlaps_the_clips(self) -> None:
        built = build(request(clips=[{"source": "a.mp4"}, {"source": "b.mp4", "transition_in": {"kind": "fade", "duration": 1}}]),
                      sources(a=4, b=3), max_seconds=300)

        self.assertIn("xfade=transition=fade:duration=0.99:offset=3.01", built.filter_graph)
        self.assertAlmostEqual(built.duration, 4 + 3 - 0.99, places=2)

    def test_no_transition_is_a_hard_cut(self) -> None:
        built = build(request(), sources(a=4, b=3), max_seconds=300)

        self.assertIn("concat=n=2:v=1:a=0", built.filter_graph)
        self.assertNotIn("xfade", built.filter_graph)
        self.assertEqual(built.duration, 7)

    def test_trim_and_speed_set_the_length(self) -> None:
        built = build(request(clips=[{"source": "a.mp4", "start": 1, "end": 5, "speed": 2}]), sources(a=10), max_seconds=300)

        self.assertIn("trim=start=1:end=5,setpts=(PTS-STARTPTS)/2", built.filter_graph)
        self.assertEqual(built.duration, 2)

    def test_an_end_past_the_source_is_clamped_and_a_start_past_it_is_refused(self) -> None:
        self.assertEqual(build(request(clips=[{"source": "a.mp4", "end": 99}]), sources(a=4), max_seconds=300).duration, 4)
        with self.assertRaisesRegex(CompositionError, "clip 0.*start 6.0s is not before its end 4.00s"):
            build(request(clips=[{"source": "a.mp4", "start": 6}]), sources(a=4), max_seconds=300)

    def test_zoom_keyframes_become_an_eased_scale_and_crop(self) -> None:
        zoom = [{"at": 1, "duration": 0.8, "x": 0.25, "y": 0.4, "scale": 2}]
        built = build(request(clips=[{"source": "a.mp4", "speed": 2, "zoom": zoom}]), sources(a=10), max_seconds=300)

        # Keyframe times are given against the clip as cut, so at 2x speed they happen twice as soon in the result.
        self.assertIn("clip((t-0.5)/0.4,0,1)", built.filter_graph)
        self.assertIn("eval=frame", built.filter_graph)
        self.assertIn("crop=1280:720:x='clip(", built.filter_graph)
        # One eased move each for the scale (used for width and for height), the x centre and the y centre.
        self.assertEqual(built.filter_graph.count("(3-2*"), 4)

    def test_an_overlay_follows_its_clip_through_the_transitions(self) -> None:
        clips = [{"source": "a.mp4"}, {"source": "b.mp4", "transition_in": {"kind": "fade", "duration": 1}}]
        built = build(request(clips=clips, overlays=[{"source": "o.png", "clip": 1, "at": 0.5, "duration": 2}]),
                      {**sources(a=4, b=3), "o.png": Source(Path("/ws/o.png"), None)}, max_seconds=300)

        # Clip 1 begins where the cross-fade does (4 - 0.99 = 3.01s in), and the overlay is 0.5s after that.
        self.assertIn("setpts=PTS-STARTPTS+3.51/TB", built.filter_graph)
        self.assertIn("between(t,3.51,5.51)", built.filter_graph)

    def test_a_still_image_is_held(self) -> None:
        built = build(request(clips=[{"source": "p.png", "hold_seconds": 2.5}]), {"p.png": Source(Path("/ws/p.png"), None)}, max_seconds=300)

        self.assertEqual(built.duration, 2.5)
        self.assertIn("-loop", built.input_args)

    def test_audio_is_trimmed_to_the_video_and_faded(self) -> None:
        audio_source = {"song.m4a": Source(Path("/ws/song.m4a"), 60, True)}
        built = build(request(audio={"source": "song.m4a", "volume": 0.5, "fade_in": 1, "fade_out": 2}), {**sources(a=4, b=3), **audio_source}, max_seconds=300)

        self.assertIn("atrim=0:7", built.filter_graph)
        self.assertIn("afade=t=out:st=5:d=2", built.filter_graph)
        self.assertEqual(built.map_args, ["-map", "[vout]", "-map", "[aout]"])

    def test_too_long_a_timeline_is_refused(self) -> None:
        with self.assertRaisesRegex(CompositionError, "limit is 5s"):
            build(request(), sources(a=4, b=3), max_seconds=5)

    def test_nothing_the_caller_wrote_reaches_ffmpeg_as_text(self) -> None:
        odd = "x';movie=/etc/passwd;'.mp4"
        built = build(request(clips=[{"source": odd, "background": "#aabbcc"}]), {odd: Source(Path("/ws/safe.mp4"), 4)}, max_seconds=300)

        self.assertNotIn("passwd", built.filter_graph + " ".join(built.input_args))
        self.assertEqual(built.input_args.count("-protocol_whitelist"), 1)
        self.assertEqual(built.input_args[1], "file,pipe", "inputs can only be files")


class ModelTests(unittest.TestCase):
    def test_bad_timelines_are_rejected_before_anything_runs(self) -> None:
        bad = [
            {"clips": []},
            {"clips": [{"source": "a.mp4", "transition_in": {"kind": "rm -rf"}}]},
            {"clips": [{"source": "a.mp4", "zoom": [{"at": 2}, {"at": 1}]}]},
            {"clips": [{"source": "a.mp4", "speed": 9}]},
            {"clips": [{"source": "a.mp4", "background": "red"}]},
            {"output": {"path": "out/v.mkv"}},
            {"output": {"path": "out/v.mp4", "width": 1281}},
            {"overlays": [{"source": "o.png", "clip": 5}]},
            {"clips": [{"source": "a.mp4", "extra": 1}]},
        ]
        for fields in bad:
            with self.assertRaises(ValidationError, msg=fields):
                request(**fields)

    def test_a_frame_needs_both_its_time_and_its_path(self) -> None:
        with self.assertRaises(ValidationError):
            ProbeRequest(request_id="r", workspace_id=WORKSPACE_ID, path="a.mp4", frame_at_seconds=1)


class EndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.env = patch.dict(os.environ, {"CLI_RUNNER_SHARED_TOKEN": "secret"})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()

    def post(self, path: str, body: dict, token: str | None = "secret") -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post(path, json=body, headers=headers)

    def compose_body(self) -> dict:
        return {"request_id": "r", "workspace_id": WORKSPACE_ID, "output": {"path": "o.mp4"}, "clips": [{"source": "a.mp4"}]}

    def test_both_endpoints_need_the_token(self) -> None:
        self.assertEqual(self.post("/v1/media/compositions", self.compose_body(), token=None).status_code, 401)
        probe = {"request_id": "r", "workspace_id": WORKSPACE_ID, "path": "a.mp4"}
        self.assertEqual(self.post("/v1/media/probes", probe, token="wrong").status_code, 401)

    def test_a_bad_timeline_is_unprocessable(self) -> None:
        self.assertEqual(self.post("/v1/media/compositions", {**self.compose_body(), "clips": []}).status_code, 422)

    def test_failures_are_mapped_to_statuses(self) -> None:
        async def impossible(*args: object) -> CompositionResponse:
            raise CompositionError("clip 0: start 9s is not before its end 4s")

        async def refused(*args: object) -> CompositionResponse:
            raise FileSystemOperationError("sandbox_violation", "Path traversal outside the workspace is blocked")

        async def broken(*args: object) -> CompositionResponse:
            raise ffmpeg.MediaError("ffmpeg couldn't build the video: boom")

        for raised, expected in ((impossible, 400), (refused, 400), (broken, 502)):
            with patch("src.infra_cli_runner.router.compose_media", raised):
                self.assertEqual(self.post("/v1/media/compositions", self.compose_body()).status_code, expected)


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg and ffprobe are not installed")
class ComposeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.files = FileSystemService(workspace_root=Path(self.root.name))
        self.workspace = self.files.workspace(WORKSPACE_ID)
        self.make("clip-a.mp4", "testsrc=duration=3:size=640x360:rate=25")
        self.make("clip-b.mp4", "smptebars=duration=3:size=1280x720:rate=30")
        self.make("tone.m4a", "sine=frequency=440:duration=20", audio=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=300x120", "-frames:v", "1", str(self.workspace / "badge.png")], check=True)

    def make(self, name: str, source: str, audio: bool = False) -> None:
        codec = ["-c:a", "aac"] if audio else ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", source, *codec, str(self.workspace / name)], check=True)

    async def made(self, **fields: object):
        fields.setdefault("clips", [{"source": "clip-a.mp4"}, {"source": "clip-b.mp4"}])
        return await compose(self.files, request(**fields))

    async def info(self, name: str) -> ffmpeg.MediaInfo:
        return await ffmpeg.probe(self.workspace / name)

    async def test_clips_of_different_sizes_and_rates_become_one_video_of_the_expected_length(self) -> None:
        clips = [{"source": "clip-a.mp4"}, {"source": "clip-b.mp4", "transition_in": {"kind": "slideleft", "duration": 0.5}}]
        result = await self.made(clips=clips, output={"path": "out/v.mp4", "fps": 30})

        info = await self.info("out/v.mp4")
        self.assertEqual((info.width, info.height, info.fps), (1280, 720, 30.0))
        self.assertAlmostEqual(info.duration, 5.5, delta=0.15)
        self.assertEqual(result.output.path, "out/v.mp4")
        self.assertFalse((self.workspace / ".runs").exists())

    async def test_zoom_overlay_speed_audio_and_webm_all_work(self) -> None:
        plain = await self.made(clips=[{"source": "clip-b.mp4"}], output={"path": "out/plain.mp4"})
        zoom = [{"at": 0.2, "duration": 0.5, "x": 0.8, "y": 0.2, "scale": 2}]
        busy = await self.made(
            clips=[{"source": "clip-b.mp4", "speed": 2, "zoom": zoom}],
            overlays=[{"source": "badge.png", "clip": 0, "at": 0.1, "duration": 1, "x": 0.1, "y": 0.1, "width": 0.3}],
            audio={"source": "tone.m4a", "fade_out": 0.5},
            output={"path": "out/busy.webm"},
        )

        info = await self.info("out/busy.webm")
        self.assertAlmostEqual(info.duration, 1.5, delta=0.2, msg="3s at 2x speed")
        self.assertTrue(info.has_audio)
        self.assertGreater(busy.output.size_bytes, 0)
        self.assertNotEqual(plain.output.size_bytes, busy.output.size_bytes)

    async def test_a_still_image_can_be_a_clip(self) -> None:
        await self.made(clips=[{"source": "badge.png", "hold_seconds": 1.5}], output={"path": "out/still.mp4"})

        self.assertAlmostEqual((await self.info("out/still.mp4")).duration, 1.5, delta=0.15)

    async def test_what_is_wrong_is_reported_plainly(self) -> None:
        with self.assertRaisesRegex(FileSystemOperationError, "missing.mp4 doesn't exist"):
            await self.made(clips=[{"source": "missing.mp4"}])
        with self.assertRaises(FileSystemOperationError):
            await self.made(clips=[{"source": "../outside.mp4"}])
        with self.assertRaisesRegex(CompositionError, "no audio"):
            await self.made(audio={"source": "clip-a.mp4"})
        with self.assertRaises(FileSystemOperationError):
            await self.made(output={"path": "../escape.mp4"})
        (self.workspace / "junk.mp4").write_bytes(b"not a video")
        with self.assertRaisesRegex(CompositionError, "junk.mp4"):
            await self.made(clips=[{"source": "junk.mp4"}])

    async def test_a_timeline_that_is_too_long_is_refused_before_ffmpeg_runs(self) -> None:
        with patch.dict(os.environ, {"MEDIA_COMPOSE_MAX_SECONDS": "2"}), self.assertRaisesRegex(CompositionError, "limit is 2s"):
            await self.made()

    async def test_ffmpeg_taking_too_long_is_stopped(self) -> None:
        with patch.dict(os.environ, {"MEDIA_COMPOSE_TIMEOUT_SECONDS": "0.05"}), self.assertRaisesRegex(ffmpeg.MediaError, "stopped"):
            await self.made(output={"path": "out/slow.mp4", "width": 1920, "height": 1080})
        self.assertFalse((self.workspace / "out/slow.mp4").exists())
        self.assertFalse((self.workspace / ".runs").exists())

    async def test_probe_reads_a_file_and_saves_a_frame_and_a_contact_sheet(self) -> None:
        result = await probe_media(self.files, ProbeRequest(
            request_id="r", workspace_id=WORKSPACE_ID, path="clip-a.mp4",
            frame_at_seconds=1.0, frame_path="qa/frame.png", sheet_path="qa/sheet.jpg",
        ))

        self.assertEqual((result.width, result.height, result.has_audio), (640, 360, False))
        self.assertAlmostEqual(result.duration_seconds, 3, delta=0.1)
        self.assertTrue((self.workspace / "qa/frame.png").read_bytes().startswith(b"\x89PNG"))
        self.assertTrue((self.workspace / "qa/sheet.jpg").read_bytes().startswith(b"\xff\xd8"))

    async def test_probe_refuses_bad_paths_before_working(self) -> None:
        for fields in ({"path": "../x.mp4"}, {"path": "nope.mp4"}, {"path": "clip-a.mp4", "sheet_path": "../s.jpg"}, {"path": "clip-a.mp4", "sheet_path": "s.txt"}):
            with self.assertRaises(FileSystemOperationError, msg=fields):
                await probe_media(self.files, ProbeRequest(request_id="r", workspace_id=WORKSPACE_ID, **fields))


if __name__ == "__main__":
    unittest.main()
