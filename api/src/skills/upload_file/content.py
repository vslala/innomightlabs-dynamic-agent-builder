from __future__ import annotations

import tempfile
from dataclasses import dataclass
from typing import IO

#: Content up to this size stays in memory while it is being fetched; more goes to a temporary file.
SPOOL_BYTES = 8 * 1024 * 1024


@dataclass
class UploadContent:
    """The bytes of one upload, as a file so a video never has to fit in memory twice."""

    file: IO[bytes]
    size: int

    @classmethod
    def from_bytes(cls, data: bytes) -> "UploadContent":
        file = tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES)
        file.write(data)
        file.seek(0)
        return cls(file=file, size=len(data))

    def head(self, count: int) -> bytes:
        self.file.seek(0)
        data = self.file.read(count)
        self.file.seek(0)
        return data

    def read_all(self) -> bytes:
        self.file.seek(0)
        data = self.file.read()
        self.file.seek(0)
        return data

    def close(self) -> None:
        self.file.close()
