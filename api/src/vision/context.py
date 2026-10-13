"""How an attached image reads in the conversation the agent sees: its id, so `read_image` can be called, and what we know of it."""

from __future__ import annotations

from src.messages.models import ImageAttachment, Message
from src.vision.models import ImageRef

NOT_DESCRIBED = "Not described yet. Call read_image with this id to see it."
#: Enough of a description to recognise the image in a recalled message.
RECALL_PREVIEW_CHARS = 200


def index_images(messages: list[Message]) -> dict[str, ImageRef]:
    """Every image the user sent in the conversation, by id: the set `read_image` may open."""
    return {
        image.image_id: ImageRef(message_sk=message.sk, index=index, attachment=image)
        for message in messages
        for index, image in enumerate(message.image_attachments)
    }


def attached_image_tag(image: ImageAttachment) -> str:
    """The block the context carries for an image on a message."""
    description = image.analysis.description if image.analysis else NOT_DESCRIBED
    return (
        f'<attached_image id="{image.image_id}" filename="{image.filename}" size="{image.width}x{image.height}">\n'
        f"Description: {description}\n"
        "</attached_image>"
    )


def recalled_image_line(image: ImageAttachment) -> str:
    """One line for `recall_conversation`, which previews messages rather than quoting them."""
    if image.analysis:
        description = image.analysis.description
        preview = description if len(description) <= RECALL_PREVIEW_CHARS else description[:RECALL_PREVIEW_CHARS] + "..."
    else:
        preview = "not described yet"
    return f"[image {image.image_id} {image.filename}: {preview}]"
