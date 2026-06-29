from __future__ import annotations

import mimetypes
from pathlib import PurePath

from src.artifacts.models import ArtifactType

DEFAULT_TEXT_MIME = "text/plain; charset=utf-8"

CODE_MIME_TYPES = {
    ".py": "text/x-python; charset=utf-8",
    ".java": "text/x-java-source; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".jsx": "text/javascript; charset=utf-8",
    ".ts": "text/typescript; charset=utf-8",
    ".tsx": "text/typescript; charset=utf-8",
    ".sql": "application/sql; charset=utf-8",
    ".go": "text/x-go; charset=utf-8",
    ".rs": "text/rust; charset=utf-8",
    ".rb": "text/x-ruby; charset=utf-8",
    ".php": "application/x-httpd-php; charset=utf-8",
    ".sh": "application/x-sh; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".xml": "application/xml; charset=utf-8",
    ".yaml": "application/yaml; charset=utf-8",
    ".yml": "application/yaml; charset=utf-8",
}


def infer_mime_type(artifact_type: ArtifactType, filename: str, override: str | None) -> str:
    if override:
        return override.strip()
    if artifact_type == "html_report":
        return "text/html; charset=utf-8"
    if artifact_type == "csv":
        return "text/csv; charset=utf-8"
    if artifact_type == "markdown":
        return "text/markdown; charset=utf-8"
    if artifact_type == "json":
        return "application/json; charset=utf-8"
    if artifact_type == "code":
        return _code_mime_type(filename)
    guessed = mimetypes.guess_type(filename)[0]
    if guessed and guessed.startswith("text/"):
        return _with_charset(guessed)
    if guessed in {"application/json", "application/xml", "application/yaml"}:
        return _with_charset(guessed)
    return DEFAULT_TEXT_MIME


def _code_mime_type(filename: str) -> str:
    suffix = PurePath(filename).suffix.lower()
    return CODE_MIME_TYPES.get(suffix, DEFAULT_TEXT_MIME)


def _with_charset(mime_type: str) -> str:
    return mime_type if "charset=" in mime_type.lower() else f"{mime_type}; charset=utf-8"
