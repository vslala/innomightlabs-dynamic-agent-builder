from __future__ import annotations

from src.messages.models import Message, MessageCanvasArtifact, MessageImage
from src.messages.responses import MessageResponseFactory


def test_message_response_factory_enriches_canvas_urls(monkeypatch):
    monkeypatch.setattr("src.messages.responses.settings.api_base_url", "https://api.example.com")
    monkeypatch.setattr("src.messages.responses.settings.frontend_url", "https://app.example.com")

    message = Message(
        conversation_id="conv-123",
        message_id="msg-456",
        role="assistant",
        content="Here is your chart",
        canvases=[
            MessageCanvasArtifact(
                artifact_id="artifact-1",
                title="Revenue",
                mime_type="text/html",
                caption="Q1 revenue by region",
            )
        ],
    )

    response = MessageResponseFactory().to_response(message)

    assert len(response.canvases) == 1
    canvas = response.canvases[0]
    assert canvas.content_url == "https://api.example.com/artifacts/artifact-1/content"
    assert canvas.open_url == "https://app.example.com/dashboard/artifacts/artifact-1"
    assert canvas.title == "Revenue"
    assert canvas.caption == "Q1 revenue by region"


def test_message_response_factory_omits_open_url_without_frontend_url(monkeypatch):
    monkeypatch.setattr("src.messages.responses.settings.api_base_url", "https://api.example.com")
    monkeypatch.setattr("src.messages.responses.settings.frontend_url", "")

    message = Message(
        conversation_id="conv-123",
        role="assistant",
        content="chart",
        canvases=[MessageCanvasArtifact(artifact_id="artifact-1", title="Chart", mime_type="text/html")],
    )

    response = MessageResponseFactory().to_response(message)

    assert response.canvases[0].open_url is None


def test_message_response_factory_enriches_images_and_canvases_independently(monkeypatch):
    monkeypatch.setattr("src.messages.responses.settings.api_base_url", "https://api.example.com")
    monkeypatch.setattr("src.messages.responses.settings.frontend_url", "https://app.example.com")

    message = Message(
        conversation_id="conv-123",
        message_id="msg-456",
        role="assistant",
        content="chart and image",
        images=[
            MessageImage(
                s3_key="key.png",
                filename="chart.png",
                mime_type="image/png",
                size_bytes=10,
            )
        ],
        canvases=[MessageCanvasArtifact(artifact_id="artifact-1", title="Chart", mime_type="text/html")],
    )

    response = MessageResponseFactory().to_response(message)

    assert len(response.images) == 1
    assert response.images[0].url.endswith(f"/messages/msg-456/images/{message.images[0].image_id}")
    assert len(response.canvases) == 1
    assert response.canvases[0].content_url == "https://api.example.com/artifacts/artifact-1/content"


def test_message_response_factory_no_canvases_returns_empty_list(monkeypatch):
    monkeypatch.setattr("src.messages.responses.settings.api_base_url", "https://api.example.com")

    message = Message(conversation_id="conv-123", role="user", content="hello")

    response = MessageResponseFactory().to_response(message)

    assert response.canvases == []
