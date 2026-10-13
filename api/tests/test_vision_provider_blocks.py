"""An image sent to the model: each provider renders the shared `ImageBlock` in its own format."""

from __future__ import annotations

import base64

from src.llm.messages import ImageBlock, normalize_messages
from src.llm.providers.anthropic import AnthropicProvider
from src.llm.providers.bedrock import BedrockProvider
from src.llm.providers.gemini import GeminiProvider
from src.llm.providers.ollama import OllamaProvider
from src.llm.providers.openai import OpenAIProvider

PNG = b"\x89PNG\r\n\x1a\nfake-image-bytes"
PNG_BASE64 = base64.b64encode(PNG).decode("ascii")


def _image_turn() -> list[dict]:
    return [
        {"role": "system", "content": "Describe images."},
        {
            "role": "user",
            "content": [
                {"type": "image", "media_type": "image/png", "data": PNG},
                {"type": "text", "text": "What is this?"},
            ],
        },
    ]


def test_image_dicts_normalise_to_image_blocks() -> None:
    blocks = normalize_messages(_image_turn())[1].content

    assert blocks[0] == ImageBlock(media_type="image/png", data=PNG)
    assert blocks[0].format == "png"


def test_anthropic_sends_a_base64_source() -> None:
    request = AnthropicProvider()._extract_system_and_messages(_image_turn())

    assert request.messages[0]["content"][0] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": PNG_BASE64},
    }


def test_bedrock_sends_raw_bytes_with_the_format_name() -> None:
    converted = BedrockProvider()._convert_messages(_image_turn())

    assert converted.messages[0]["content"][0] == {"image": {"format": "png", "source": {"bytes": PNG}}}


def test_openai_sends_an_input_image_data_url() -> None:
    items = OpenAIProvider()._convert_messages(_image_turn())

    content = items[1]["content"]
    assert content[0] == {
        "type": "input_image",
        "image_url": f"data:image/png;base64,{PNG_BASE64}",
        "detail": "auto",
    }
    assert content[1] == {"type": "input_text", "text": "What is this?"}


def test_gemini_sends_inline_bytes() -> None:
    converted = GeminiProvider()._convert_messages(_image_turn())

    part = converted.messages[0].parts[0]
    assert part.inline_data.data == PNG
    assert part.inline_data.mime_type == "image/png"


def test_ollama_puts_images_beside_the_text() -> None:
    messages = OllamaProvider()._convert_messages(_image_turn())

    assert messages[1] == {"role": "user", "content": "What is this?", "images": [PNG_BASE64]}
