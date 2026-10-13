"""Why an image was refused, in terms every surface can show."""

from __future__ import annotations


class ImageInputError(Exception):
    """A refusal with a stable `code` the clients can switch on and a `message` they can show.

    Rendered as `{"detail": {"code", "message"}}` by the handler in `src/exceptions.py`.
    """

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
