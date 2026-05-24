"""Models for downloadable plugin artifacts."""

from pydantic import BaseModel, Field


class PluginDownloadSummary(BaseModel):
    """Public metadata for a downloadable plugin."""

    id: str
    name: str
    kind: str
    tagline: str
    description: str
    version: str
    platform: str
    filename: str
    download_url: str
    icon_url: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None


class PluginDownloadDetail(PluginDownloadSummary):
    """Full plugin details including README markdown."""

    readme_markdown: str = Field(default="")


class PluginDownloadsResponse(BaseModel):
    """Response containing all available plugin downloads."""

    plugins: list[PluginDownloadSummary]
