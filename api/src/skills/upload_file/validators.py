from __future__ import annotations

from typing import Protocol

from src.artifacts.models import ArtifactType
from src.skills.league_insights_report.html_safety import extract_html_document, validate_safe_report_html
from src.skills.upload_file.models import UploadFileRequest


class ArtifactContentValidator(Protocol):
    def validate(self, request: UploadFileRequest, body: bytes) -> bytes:
        ...


class HtmlArtifactValidator:
    def validate(self, request: UploadFileRequest, body: bytes) -> bytes:
        del request
        html = extract_html_document(body.decode("utf-8"))
        validate_safe_report_html(html)
        return html.encode("utf-8")


class NoopArtifactValidator:
    def validate(self, request: UploadFileRequest, body: bytes) -> bytes:
        del request
        return body


class ArtifactValidatorRegistry:
    def __init__(self):
        self._noop = NoopArtifactValidator()
        self._validators: dict[str, ArtifactContentValidator] = {
            "html_report": HtmlArtifactValidator(),
        }

    def validator_for(self, artifact_type: ArtifactType) -> ArtifactContentValidator:
        return self._validators.get(str(artifact_type), self._noop)
