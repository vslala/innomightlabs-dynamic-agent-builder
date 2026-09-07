from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_CANVAS_HTML_BYTES = 6 * 1024 * 1024  # 6 MB cap per canvas artifact
CANVAS_ARTIFACT_FILENAME = "canvas.html"


class RenderCanvasRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    caption: str | None = Field(default=None, max_length=500)
    html: str

    @model_validator(mode="after")
    def normalize(self) -> "RenderCanvasRequest":
        self.title = self.title.strip()
        self.caption = self.caption.strip() if self.caption else None
        if not self.title:
            raise ValueError("title is required")
        if not self.html.strip():
            raise ValueError("html is required")
        if len(self.html.encode("utf-8")) > MAX_CANVAS_HTML_BYTES:
            raise ValueError(f"html exceeds the {MAX_CANVAS_HTML_BYTES // (1024 * 1024)} MB limit")
        return self
