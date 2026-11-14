"""Checking a document against what a network accepts. Unlike an image it is never re-encoded: a network gets the file
as it is, once its name, its first bytes and its size all agree with the network's limits."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath
from typing import Protocol

from src.connectors.social.networks.base import DocumentLimits, PreparedDocument, PublishError, PublishErrorKind

#: Office files from 2007 on are zip archives; older ones are OLE compound files
_ZIP, _OLE = b"PK\x03\x04", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

#: Every document format any network takes: its MIME type and how its bytes start
FORMATS: dict[str, tuple[str, bytes]] = {
    ".pdf": ("application/pdf", b"%PDF-"),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", _ZIP),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", _ZIP),
    ".doc": ("application/msword", _OLE),
    ".ppt": ("application/vnd.ms-powerpoint", _OLE),
}


class DocumentFacts(Protocol):
    """What planning needs to know about a document, without reading it."""

    @property
    def filename(self) -> str: ...

    @property
    def size_bytes(self) -> int: ...


@dataclass(frozen=True)
class SourceDocument:
    data: bytes
    filename: str
    title: str = ""

    @property
    def size_bytes(self) -> int:
        return len(self.data)


def extension(filename: str) -> str:
    return PurePath(filename).suffix.lower()


def megabytes(size: int) -> str:
    return f"{size / (1024 * 1024):.1f} MB"


def prepare_document(source: SourceDocument, limits: DocumentLimits) -> PreparedDocument:
    """The document as the network takes it. Raises PublishError(REJECTED) when it isn't one the network posts."""
    suffix = extension(source.filename)
    if suffix not in limits.formats or suffix not in FORMATS:
        raise PublishError(PublishErrorKind.REJECTED, f"{source.filename} is not a {', '.join(limits.formats)} document")
    mime_type, magic = FORMATS[suffix]
    if not source.data.startswith(magic):
        raise PublishError(PublishErrorKind.REJECTED, f"{source.filename} is not a valid {suffix[1:].upper()} file")
    if source.size_bytes > limits.max_bytes:
        raise PublishError(PublishErrorKind.REJECTED,
                           f"{source.filename} is {megabytes(source.size_bytes)}; the limit is {megabytes(limits.max_bytes)}")
    title = " ".join(source.title.split()) or PurePath(source.filename).stem
    return PreparedDocument(data=source.data, filename=source.filename, mime_type=mime_type, title=title)
