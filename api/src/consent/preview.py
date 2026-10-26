"""What the person is shown before an action runs: a title and typed blocks the SPA renders one way each.

A skill composes these in its preview handler; an action without one gets `default_preview`, which shows every
argument, so a missing or failing preview can never hide what will run. See docs/LLD-action-consent.md.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Callable, Literal

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    kind: Literal["text"] = "text"
    label: str | None = None
    value: str
    format: Literal["plain", "markdown"] = "plain"
    #: The argument this shows; the person can edit it when it is one of the request's editable arguments.
    argument: str | None = None


class EmailBlock(BaseModel):
    kind: Literal["email"] = "email"
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str = ""
    body: str = ""
    #: Rendered in a sandboxed frame, never inline.
    html_body: str | None = None
    #: The arguments holding the subject and body, so they can be edited in place.
    arguments: dict[Literal["subject", "body"], str] = Field(default_factory=dict)


class PreviewImage(BaseModel):
    s3_key: str
    alt_text: str | None = None


class ImagesBlock(BaseModel):
    kind: Literal["images"] = "images"
    label: str | None = None
    #: Stored as S3 keys and presigned when read, so a stored preview never holds a URL that expires.
    items: list[PreviewImage]


class PreviewTarget(BaseModel):
    label: str
    detail: str | None = None
    will_run: bool = True
    reason: str | None = None


class TargetsBlock(BaseModel):
    """Where the action goes, and what will be skipped and why."""

    kind: Literal["targets"] = "targets"
    label: str = "Goes to"
    items: list[PreviewTarget]


class PreviewField(BaseModel):
    label: str
    value: str
    argument: str | None = None


class FieldsBlock(BaseModel):
    kind: Literal["fields"] = "fields"
    label: str | None = None
    items: list[PreviewField]


class PreviewGrant(BaseModel):
    key: str
    title: str
    warning: str | None = None
    checked: bool = False
    #: The agent already has a standing consent for it, so it is ticked and can't be unticked here.
    always_allowed: bool = False


class GrantsBlock(BaseModel):
    """Actions an automation's agent step may take without asking; the person ticks the ones to allow."""

    kind: Literal["grants"] = "grants"
    label: str
    #: The edit that carries the ticked keys, e.g. `grants:<node_id>`.
    argument: str
    items: list[PreviewGrant]


class CodeBlock(BaseModel):
    kind: Literal["code"] = "code"
    label: str | None = None
    language: str = "json"
    value: str


class WarningBlock(BaseModel):
    kind: Literal["warning"] = "warning"
    text: str


ConsentBlock = Annotated[
    TextBlock | EmailBlock | ImagesBlock | TargetsBlock | FieldsBlock | GrantsBlock | CodeBlock | WarningBlock,
    Field(discriminator="kind"),
]


class ConsentPreview(BaseModel):
    title: str
    summary: str | None = None
    blocks: list[ConsentBlock] = Field(default_factory=list)
    #: A preview handler may narrow the manifest's editable arguments for this call (no body edit beside an HTML body).
    editable: list[str] | None = None

    def with_images(self, url_for: Callable[[str], str]) -> list[dict[str, Any]]:
        """The blocks as the SPA receives them: image keys replaced by URLs it can load."""
        blocks = []
        for block in self.blocks:
            shown = block.model_dump(mode="json")
            if isinstance(block, ImagesBlock):
                shown["items"] = [{"url": url_for(image.s3_key), "alt_text": image.alt_text} for image in block.items]
            blocks.append(shown)
        return blocks


def default_preview(title: str, arguments: dict[str, Any], input_schema: dict[str, Any]) -> ConsentPreview:
    """Every argument, labelled from the schema, and the exact call as JSON."""
    properties = input_schema.get("properties", {})
    fields = [
        PreviewField(label=_label(name, properties.get(name)), value=str(value), argument=name)
        for name, value in arguments.items()
        if isinstance(value, (str, int, float, bool))
    ]
    blocks: list[ConsentBlock] = [FieldsBlock(items=fields)] if fields else []
    blocks.append(CodeBlock(label="Exact arguments", value=json.dumps(arguments, indent=2, ensure_ascii=False)))
    return ConsentPreview(title=title, blocks=blocks)


def _label(name: str, schema: Any) -> str:
    title = schema.get("title") if isinstance(schema, dict) else None
    return title if isinstance(title, str) and title.strip() else name.replace("_", " ").capitalize()
