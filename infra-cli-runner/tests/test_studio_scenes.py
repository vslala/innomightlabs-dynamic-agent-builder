from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from playwright.async_api import async_playwright
from pydantic import ValidationError

from main import app
from src.infra_cli_runner.browser import BrowserRenderer, RenderError
from src.infra_cli_runner.filesystem import FileSystemOperationError, FileSystemService
from src.infra_cli_runner.media import ffmpeg
from src.infra_cli_runner.studio.models import SceneParams, SceneRequest, SceneResponse
from src.infra_cli_runner.studio.scenes import _scene_files, render_scene
from src.infra_cli_runner.studio.templates import SCENE_TEMPLATES, template_for

WORKSPACE_ID = "e" * 48
HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
BASE = {"request_id": "r", "workspace_id": WORKSPACE_ID, "duration_seconds": 1, "output_path": "scenes/s.mp4"}


def chromium_installed() -> bool:
    import asyncio

    async def probe() -> bool:
        async with async_playwright() as playwright:
            return os.path.exists(playwright.chromium.executable_path)

    return asyncio.run(probe())


class RequestTests(unittest.TestCase):
    def test_a_scene_is_a_template_or_a_file_and_never_both(self) -> None:
        params = {"heading": "Hello"}
        SceneRequest(**BASE, template="title", params=params)
        SceneRequest(**BASE, scene_path="scenes/mine.html")
        for fields in (
            {}, {"template": "title"}, {"params": params}, {"template": "title", "params": params, "scene_path": "a.html"},
            {"scene_path": "a.txt"}, {"template": "nope", "params": params}, {"template": "title", "params": {"heading": ""}},
            {"template": "title", "params": {"heading": "x", "accent": "red"}}, {"template": "title", "params": {"heading": "x", "css": "x"}},
            {"template": "title", "params": params, "output_path": "s.gif"}, {"template": "title", "params": params, "duration_seconds": 99},
        ):
            with self.assertRaises(ValidationError, msg=fields):
                SceneRequest(**{**BASE, **fields})  # type: ignore[arg-type]

    def test_what_a_caller_writes_is_text_not_markup(self) -> None:
        hostile = "<script>alert(1)</script><img src=x>"
        for template in SCENE_TEMPLATES:
            html = template.html(SceneParams(heading=hostile, subheading=hostile, eyebrow=hostile, footer=hostile), 3)
            self.assertNotIn("<script", html, template.name)
            self.assertNotIn("<img", html, template.name)
            self.assertIn("&lt;script&gt;", html, template.name)

    def test_every_template_leaves_the_stage_before_it_ends(self) -> None:
        for template in SCENE_TEMPLATES:
            self.assertIn("animation:leave 0.45s ease-in 2.550s both", template.html(SceneParams(heading="x"), 3).replace("\n", ""), template.name)

    def test_templates_are_found_by_name(self) -> None:
        self.assertEqual({t.name for t in SCENE_TEMPLATES}, {"title", "outro", "lower_third"})
        self.assertTrue(template_for("lower_third").transparent)
        self.assertFalse(template_for("title").transparent)


class EndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.env = patch.dict(os.environ, {"CLI_RUNNER_SHARED_TOKEN": "secret"})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()

    def post(self, body: dict, token: str | None = "secret") -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.post("/v1/browser/scenes", json={**BASE, "template": "title", "params": {"heading": "Hi"}, **body}, headers=headers)

    def test_requires_the_bearer_token(self) -> None:
        self.assertEqual(self.post({}, token=None).status_code, 401)

    def test_a_malformed_request_is_unprocessable(self) -> None:
        self.assertEqual(self.post({"template": "nope"}).status_code, 422)

    def test_failures_are_mapped_to_statuses(self) -> None:
        def raising(error: Exception):  # type: ignore[no-untyped-def]
            async def raiser(*args: object) -> SceneResponse:
                raise error

            return raiser

        cases = (
            (RenderError("couldn't render the scene"), 502),
            (ffmpeg.MediaError("ffmpeg couldn't encode the scene"), 502),
            (FileSystemOperationError("invalid_path", "a transparent scene keeps its alpha only as .webm"), 400),
        )
        for error, expected in cases:
            with patch("src.infra_cli_runner.router.render_scene", raising(error)):
                self.assertEqual(self.post({}).status_code, expected, error)


class SceneAssetTests(unittest.TestCase):
    """What a scene's own page may load: the workspace's web assets, and nothing else."""

    def setUp(self) -> None:
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.files = FileSystemService(workspace_root=Path(self.root.name))
        self.workspace = self.files.workspace(WORKSPACE_ID)
        (self.workspace / "style.css").write_text("body{}")
        (self.workspace / "secrets.txt").write_text("nope")
        (self.workspace / "sub").mkdir()
        (self.workspace / "sub/logo.svg").write_text("<svg/>")
        (Path(self.root.name) / "outside.css").write_text("outside")
        os.symlink(Path(self.root.name) / "outside.css", self.workspace / "link.css")
        self.read = _scene_files(self.files, self.workspace, "<html>template</html>")

    def test_web_assets_are_served_with_their_type(self) -> None:
        css, svg = self.read("style.css"), self.read("sub/logo.svg")
        self.assertEqual((css.status, css.headers["content-type"], css.body), (200, "text/css", b"body{}"))
        self.assertEqual(svg.headers["content-type"], "image/svg+xml")

    def test_the_template_page_is_served_from_memory(self) -> None:
        self.assertEqual(self.read("__template__.html").body, b"<html>template</html>")

    def test_nothing_else_is_served(self) -> None:
        for path in ("secrets.txt", "missing.css", "../outside.css", "%2e%2e/outside.css", "link.css", "sub", ".runs/x.css", "/etc/passwd"):
            self.assertIsNone(self.read(path), path)


@unittest.skipUnless(chromium_installed() and HAS_FFMPEG, "Chromium and ffmpeg are needed: `uv run playwright install chromium`")
class RenderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.files = FileSystemService(workspace_root=Path(self.root.name))
        self.workspace = self.files.workspace(WORKSPACE_ID)
        self.renderer = BrowserRenderer()
        self.addAsyncCleanup(self.renderer.close)

    async def render(self, **fields: object) -> SceneResponse:
        return await render_scene(self.renderer, self.files, SceneRequest(**{**BASE, **fields}))  # type: ignore[arg-type]

    def frame_bytes(self, name: str, at: float) -> bytes:
        return subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-ss", str(at), "-i", str(self.workspace / name), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, check=True,
        ).stdout

    def pixel(self, name: str, at: float, x: int, y: int) -> tuple[int, ...]:
        raw = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-ss", str(at), "-i", str(self.workspace / name), "-frames:v", "1",
             "-vf", f"crop=2:2:{x}:{y}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, check=True,
        ).stdout
        return tuple(raw[:3])

    async def test_a_template_becomes_a_video_that_animates(self) -> None:
        result = await self.render(template="title", params={"heading": "Hello world", "subheading": "Sub"}, duration_seconds=1.5)

        info = await ffmpeg.probe(self.workspace / "scenes/s.mp4")
        self.assertEqual((result.frames, result.output.duration_seconds), (45, 1.5))
        self.assertAlmostEqual(info.duration, 1.5, delta=0.1)
        self.assertEqual((info.width, info.height, info.fps), (1280, 720, 30.0))
        self.assertNotEqual(self.frame_bytes("scenes/s.mp4", 0.05), self.frame_bytes("scenes/s.mp4", 0.9), "the heading comes in")
        self.assertFalse((self.workspace / ".runs").exists())

    async def test_the_same_scene_renders_to_the_same_frames(self) -> None:
        params = {"heading": "Same every time"}
        await self.render(template="title", params=params, output_path="scenes/one.mp4")
        await self.render(template="title", params=params, output_path="scenes/two.mp4")

        for at in (0.2, 0.6):
            self.assertEqual(self.frame_bytes("scenes/one.mp4", at), self.frame_bytes("scenes/two.mp4", at), f"frame at {at}s")

    async def test_a_lower_third_keeps_its_transparency_as_webm(self) -> None:
        await self.render(template="lower_third", params={"heading": "Name", "subheading": "Role"}, output_path="scenes/lt.webm", duration_seconds=1.2)

        tags = json.loads(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream_tags=alpha_mode", "-of", "json", str(self.workspace / "scenes/lt.webm")],
            capture_output=True, check=True, text=True).stdout)["streams"][0]["tags"]
        self.assertEqual(tags["alpha_mode"], "1")
        with self.assertRaisesRegex(FileSystemOperationError, "alpha only as .webm"):
            await self.render(template="lower_third", params={"heading": "x"}, output_path="scenes/lt.mp4")

    async def test_your_own_page_loads_its_assets_from_the_workspace(self) -> None:
        (self.workspace / "style.css").write_text("html,body{background:#00ff00}")
        (self.workspace / "mine.html").write_text('<!doctype html><link rel="stylesheet" href="./style.css"><body></body>')

        await self.render(scene_path="mine.html")

        red, green, blue = self.pixel("scenes/s.mp4", 0.3, 640, 360)
        self.assertGreater(green, 200)
        self.assertLess(red + blue, 90)

    async def test_a_page_cannot_reach_beyond_the_workspace_or_the_network(self) -> None:
        (Path(self.root.name) / "outside.css").write_text("html,body{background:#ff0000}")
        (self.workspace / "mine.html").write_text(
            '<!doctype html><link rel="stylesheet" href="../outside.css"><link rel="stylesheet" href="http://127.0.0.1:9/x.css">'
            "<style>html,body{background:#0000ff}</style><body></body>"
        )

        await self.render(scene_path="mine.html")

        red, _, blue = self.pixel("scenes/s.mp4", 0.3, 640, 360)
        self.assertGreater(blue, 200)
        self.assertLess(red, 60)

    async def test_what_is_wrong_is_reported_before_rendering(self) -> None:
        for fields in (
            {"scene_path": "missing.html"}, {"scene_path": "../x.html"}, {"template": "title", "params": {"heading": "x"}, "output_path": "../x.mp4"},
        ):
            with self.assertRaises(FileSystemOperationError, msg=fields):
                await self.render(**fields)
        self.assertFalse((self.workspace / ".runs").exists())

    async def test_a_page_that_never_gets_ready_is_reported(self) -> None:
        (self.workspace / "stuck.html").write_text("<!doctype html><script>window.__studioReady = new Promise(() => {})</script>")

        with patch("src.infra_cli_runner.studio.scenes.READY_TIMEOUT_SECONDS", 0.5), self.assertRaisesRegex(RenderError, "never became ready"):
            await self.render(scene_path="stuck.html")
        self.assertFalse((self.workspace / ".runs").exists())


if __name__ == "__main__":
    unittest.main()
